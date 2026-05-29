import socket
import os
import json


BUFFER_SIZE = 4096
MAX_HEADER_SIZE = 8192


def send_json(sock, data):
    """
    Sends a Python dictionary as a JSON message.
    The newline helps the server know where this message ends.
    """
    message = json.dumps(data) + "\n"
    sock.sendall(message.encode("utf-8"))


def recv_line(sock):
    """
    Receives data until a newline is found.
    This is how the client receives one full JSON response from the server.
    """
    data = bytearray()

    while True:
        chunk = sock.recv(1)

        if not chunk:
            if len(data) == 0:
                return None
            raise ConnectionError("Server disconnected during response.")

        if chunk == b"\n":
            break

        data.extend(chunk)

        if len(data) > MAX_HEADER_SIZE:
            raise ValueError("Response header too large.")

    return data.decode("utf-8")


def recv_json(sock):
    """
    Receives a JSON response from the server and turns it into a dictionary.
    """
    line = recv_line(sock)

    if line is None:
        return None

    try:
        return json.loads(line)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON response from server.")


def print_response(response):
    """
    Prints server responses in a clean way.
    """
    if response is None:
        print("[ERROR] No response from server.")
        return

    status = response.get("status", "UNKNOWN")
    message = response.get("message", "")

    print(f"[{status}] {message}")

    if "sha256" in response:
        print(f"[SHA256] {response['sha256']}")


def send_file(sock, path):
    """
    Sends a file to the server.
    First we send the filename and size, then we send the actual file bytes.
    """
    if not os.path.exists(path):
        print("[ERROR] File does not exist.")
        return

    if not os.path.isfile(path):
        print("[ERROR] Path is not a file.")
        return

    filename = os.path.basename(path)
    file_size = os.path.getsize(path)

    # Tell the server what file we are about to send.
    send_json(sock, {
        "cmd": "FILE",
        "filename": filename,
        "size": file_size
    })

    response = recv_json(sock)

    if response is None:
        print("[ERROR] Server disconnected.")
        return

    # The server must say READY before we send the file bytes.
    if response.get("status") != "READY":
        print_response(response)
        return

    print_response(response)

    # Send the file in chunks instead of loading a huge file all at once.
    with open(path, "rb") as file:
        while True:
            chunk = file.read(BUFFER_SIZE)

            if not chunk:
                break

            sock.sendall(chunk)

    # After the file is sent, wait for the final server confirmation.
    final_response = recv_json(sock)
    print_response(final_response)


def main():
    host = input("Server IP address [127.0.0.1]: ").strip()
    port_text = input("Server port [5050]: ").strip()

    if host == "":
        host = "127.0.0.1"

    if port_text == "":
        port = 5050
    else:
        try:
            port = int(port_text)
        except ValueError:
            print("[ERROR] Invalid port number.")
            return

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client_socket.connect((host, port))
        print(f"[CONNECTED] Connected to server at {host}:{port}")

        print("\nAvailable commands:")
        print("LOGIN username")
        print("MSG your message here")
        print("FILE path/to/file")
        print("QUIT\n")

        while True:
            user_input = input("> ").strip()

            if user_input == "":
                print("[ERROR] Empty command.")
                continue

            # Split the command from the rest of the text.
            # Example: "MSG hello there" becomes command="MSG", argument="hello there".
            parts = user_input.split(" ", 1)
            command = parts[0].upper()
            argument = parts[1] if len(parts) > 1 else ""

            if command == "LOGIN":
                send_json(client_socket, {
                    "cmd": "LOGIN",
                    "user": argument
                })

                response = recv_json(client_socket)
                print_response(response)

            elif command == "MSG":
                send_json(client_socket, {
                    "cmd": "MSG",
                    "text": argument
                })

                response = recv_json(client_socket)
                print_response(response)

            elif command == "FILE":
                if argument.strip() == "":
                    print("[ERROR] Usage: FILE path/to/file")
                    continue

                send_file(client_socket, argument)

            elif command == "QUIT":
                send_json(client_socket, {
                    "cmd": "QUIT"
                })

                response = recv_json(client_socket)
                print_response(response)
                break

            else:
                # Send unknown commands too, so the server can reply with an error.
                send_json(client_socket, {
                    "cmd": command
                })

                response = recv_json(client_socket)
                print_response(response)

    except ConnectionRefusedError:
        print("[ERROR] Could not connect to server. Make sure server.py is running.")

    except ConnectionError as error:
        print(f"[ERROR] {error}")

    except OSError as error:
        print(f"[NETWORK ERROR] {error}")

    finally:
        client_socket.close()
        print("[CLOSED] Client closed.")


if __name__ == "__main__":
    main()