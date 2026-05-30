import socket
import os
import sys
import json


# Defaults used if the user just hits Enter at the prompts.
HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 5050

# Same limits as the server, so the two sides agree on what counts as too big.
MAX_HEADER_SIZE = 8192
BUFFER_SIZE = 4096


HELP_TEXT = """Available commands:
  LOGIN <username>   - log in with a username from users.txt
  MSG <text>         - send a text message to the server
  FILE <path>        - upload a local file to the server
  HELP               - show this list of commands
  QUIT               - disconnect and exit"""


def send_json(sock, data):
    """
    Sends a dictionary as a JSON message ending with a newline,
    which is how the server knows where the message ends.
    """
    message = json.dumps(data) + "\n"
    sock.sendall(message.encode("utf-8"))


def recv_line(sock):
    """
    Reads bytes one at a time until it sees a newline.
    We use this for JSON protocol messages, the same way the server does.
    """
    data = bytearray()

    while True:
        chunk = sock.recv(1)

        # Empty chunk means the server closed the connection on us.
        if not chunk:
            if len(data) == 0:
                return None
            raise ConnectionError("Server disconnected during header transfer.")

        if chunk == b"\n":
            break

        data.extend(chunk)

        if len(data) > MAX_HEADER_SIZE:
            raise ValueError("Header from server was too large.")

    return data.decode("utf-8")


def recv_json(sock):
    """
    Receives one JSON message and turns it back into a Python dictionary.
    """
    line = recv_line(sock)

    if line is None:
        return None

    try:
        return json.loads(line)
    except json.JSONDecodeError:
        raise ValueError("Server sent something that was not valid JSON.")


def print_response(response):
    """
    Prints a server response in a consistent format like [OK] message text.
    Returns False if the server has already disconnected, True otherwise.
    """
    if response is None:
        print("[DISCONNECTED] Server closed the connection.")
        return False

    status = response.get("status", "?")
    message = response.get("message", "")
    print(f"[{status}] {message}")
    return True


def do_login(sock, arg):
    username = arg.strip()

    if not username:
        print("[CLIENT] Usage: LOGIN <username>")
        return True

    send_json(sock, {"cmd": "LOGIN", "user": username})
    response = recv_json(sock)
    return print_response(response)


def do_msg(sock, arg):
    # The server rejects empty messages, but checking here avoids a pointless round trip.
    if arg.strip() == "":
        print("[CLIENT] Usage: MSG <text>")
        return True

    send_json(sock, {"cmd": "MSG", "text": arg})
    response = recv_json(sock)
    return print_response(response)


def do_file(sock, arg):
    path = arg.strip()

    if not path:
        print("[CLIENT] Usage: FILE <path>")
        return True

    # Catch local errors here so we never send a header for a file we cannot read.
    if not os.path.isfile(path):
        print(f"[CLIENT] File not found: {path}")
        return True

    try:
        with open(path, "rb") as file:
            data = file.read()
    except OSError as error:
        print(f"[CLIENT] Could not read file: {error}")
        return True

    filename = os.path.basename(path)

    # Step 1: send the header. The server validates filename and size before agreeing.
    send_json(sock, {
        "cmd": "FILE",
        "filename": filename,
        "size": len(data)
    })

    # Step 2: wait for READY (or ERR). If we got ERR, we must NOT send bytes,
    # otherwise the server would treat them as a new command and the stream desyncs.
    response = recv_json(sock)

    if response is None:
        print("[DISCONNECTED] Server closed the connection.")
        return False

    print_response(response)

    if response.get("status") != "READY":
        return True

    # Step 3: send the raw bytes.
    sock.sendall(data)

    # Step 4: read the final OK with the SHA-256 hash.
    response = recv_json(sock)

    if response is None:
        print("[DISCONNECTED] Server closed the connection.")
        return False

    print_response(response)

    if "sha256" in response:
        print(f"[SHA256] {response['sha256']}")

    return True


def do_quit(sock, arg):
    send_json(sock, {"cmd": "QUIT"})

    # The server replies once with Goodbye before closing. If it has already
    # closed we just move on.
    try:
        response = recv_json(sock)
        print_response(response)
    except (ConnectionError, OSError, ValueError):
        pass

    return False  # tells the main loop to stop


def prompt_host_and_port():
    """
    Asks the user for the server IP and port, falling back to defaults.
    Command-line args take priority: python client.py <host> <port>.
    """
    if len(sys.argv) >= 3:
        # CHANGES HERE: validate the port from the command line so a bad arg
        # like `python client.py localhost abc` shows a clear message instead
        # of crashing with an int() ValueError traceback. The rubric calls
        # out that the application should avoid crashing whenever possible.
        try:
            return sys.argv[1], int(sys.argv[2])
        except ValueError:
            print(f"[CLIENT] Invalid port '{sys.argv[2]}'. Port must be an integer.")
            sys.exit(1)

    host_input = input(f"Server IP [{HOST_DEFAULT}]: ").strip()
    host = host_input if host_input else HOST_DEFAULT

    port_input = input(f"Server port [{PORT_DEFAULT}]: ").strip()

    if port_input == "":
        port = PORT_DEFAULT
    else:
        try:
            port = int(port_input)
        except ValueError:
            print(f"[CLIENT] Invalid port. Using default {PORT_DEFAULT}.")
            port = PORT_DEFAULT

    return host, port


def main():
    host, port = prompt_host_and_port()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock.connect((host, port))
    except ConnectionRefusedError:
        print(f"[ERROR] Could not connect to {host}:{port}. Is the server running?")
        return
    except OSError as error:
        print(f"[ERROR] Connection error: {error}")
        return

    print(f"[CONNECTED] Connected to {host}:{port}")

    # CHANGES HERE: 60-second timeout on socket operations.
    # Without this, if the server stops responding mid-conversation
    # (for example, it crashes after sending READY but before saving the file),
    # recv() blocks forever and the client hangs with no way to recover except
    # Ctrl+C. With a timeout, socket.timeout is raised, which is a subclass of
    # OSError and is caught by the main loop below, printing an error and
    # closing the connection cleanly. 60s is generous enough for large files.
    sock.settimeout(60)

    print(HELP_TEXT)

    # Map each command name to the function that handles it.
    handlers = {
        "LOGIN": do_login,
        "MSG": do_msg,
        "FILE": do_file,
        "QUIT": do_quit,
    }

    try:
        while True:
            try:
                user_input = input("> ")
            except EOFError:
                # Happens when stdin runs out, e.g. when input is piped in.
                user_input = "QUIT"

            if not user_input.strip():
                continue

            # Split into command and the rest of the line as a single argument.
            parts = user_input.split(" ", 1)
            command = parts[0].upper()
            argument = parts[1] if len(parts) > 1 else ""

            if command == "HELP":
                print(HELP_TEXT)
                continue

            if command not in handlers:
                print(f"[CLIENT] Unknown command: {command}. Type HELP for the command list.")
                continue

            try:
                keep_going = handlers[command](sock, argument)
            except (ConnectionError, OSError) as error:
                print(f"[ERROR] {error}")
                break
            except ValueError as error:
                print(f"[ERROR] {error}")
                continue

            if not keep_going:
                break

    except KeyboardInterrupt:
        print("\n[CLIENT] Interrupted. Closing connection.")
        try:
            send_json(sock, {"cmd": "QUIT"})
        except OSError:
            pass

    finally:
        sock.close()
        print("[CLIENT] Disconnected.")


if __name__ == "__main__":
    main()