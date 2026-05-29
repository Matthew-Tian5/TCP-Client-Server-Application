import socket
import os
import json
import hashlib


# The server listens on this IP and port.
# 0.0.0.0 means it accepts connections from this machine and other machines on the network.
HOST = "0.0.0.0"
PORT = 5050

# This file stores the allowed usernames for LOGIN.
USERS_FILE = "users.txt"

# Any files the client sends will be saved inside this folder.
RECEIVED_DIR = "server_received_files"

# These limits help avoid weird or extremely large protocol headers.
MAX_HEADER_SIZE = 8192
BUFFER_SIZE = 4096


def load_users(filename):
    """
    Reads valid usernames from users.txt.
    Each line in the file is treated as one valid username.
    """
    users = set()

    if not os.path.exists(filename):
        print(f"[ERROR] Missing {filename}. Create it and add valid usernames.")
        return users

    with open(filename, "r", encoding="utf-8") as file:
        for line in file:
            username = line.strip()

            # Ignore empty lines so the file can have spacing if needed.
            if username:
                users.add(username)

    return users


def send_json(conn, data):
    """
    Sends a dictionary as a JSON message.
    The newline at the end tells the receiver where the message ends.
    """
    message = json.dumps(data) + "\n"
    conn.sendall(message.encode("utf-8"))


def recv_line(conn):
    """
    Reads from the socket until it finds a newline.
    We use this for JSON protocol messages.
    """
    data = bytearray()

    while True:
        chunk = conn.recv(1)

        # If recv gives us nothing, the client probably disconnected.
        if not chunk:
            if len(data) == 0:
                return None
            raise ConnectionError("Client disconnected during header transfer.")

        if chunk == b"\n":
            break

        data.extend(chunk)

        if len(data) > MAX_HEADER_SIZE:
            raise ValueError("Header too large.")

    return data.decode("utf-8")


def recv_json(conn):
    """
    Receives one JSON message and converts it back into a Python dictionary.
    """
    line = recv_line(conn)

    if line is None:
        return None

    try:
        return json.loads(line)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON format.")


def recv_exact(conn, size):
    """
    Receives exactly 'size' bytes.
    This is important for file transfer because files are sent as raw bytes.
    """
    data = bytearray()
    remaining = size

    while remaining > 0:
        chunk = conn.recv(min(BUFFER_SIZE, remaining))

        if not chunk:
            raise ConnectionError("Client disconnected during file transfer.")

        data.extend(chunk)
        remaining -= len(chunk)

    return bytes(data)


def safe_filename(filename):
    """
    Keeps only the actual filename, not any folder path.
    This prevents the client from saving files outside the server folder.
    """
    filename = os.path.basename(filename)

    if filename == "":
        return None

    return filename


def unique_path(directory, filename):
    """
    If a file with the same name already exists, create a new name.
    Example: test.txt becomes test_1.txt instead of overwriting the old file.
    """
    base, ext = os.path.splitext(filename)
    path = os.path.join(directory, filename)
    counter = 1

    while os.path.exists(path):
        new_name = f"{base}_{counter}{ext}"
        path = os.path.join(directory, new_name)
        counter += 1

    return path


def handle_client(conn, addr, valid_users):
    """
    Handles one connected client.
    The assignment only requires one client at a time, so no threading is needed.
    """
    print(f"[CONNECTED] Client connected from {addr}")

    # This stays None until the client successfully logs in.
    logged_in_user = None

    try:
        while True:
            try:
                request = recv_json(conn)
            except ValueError as error:
                send_json(conn, {
                    "status": "ERR",
                    "message": str(error)
                })
                continue

            # None means the client disconnected without sending more data.
            if request is None:
                print(f"[DISCONNECTED] Client {addr} disconnected.")
                break

            command = request.get("cmd", "").upper()

            if command == "LOGIN":
                username = request.get("user", "").strip()

                if not username:
                    send_json(conn, {
                        "status": "ERR",
                        "message": "Username cannot be empty."
                    })

                elif username not in valid_users:
                    send_json(conn, {
                        "status": "ERR",
                        "message": "Invalid username."
                    })

                else:
                    logged_in_user = username
                    print(f"[LOGIN] {username} logged in from {addr}")

                    send_json(conn, {
                        "status": "OK",
                        "message": f"Welcome, {username}."
                    })

            elif command == "MSG":
                # We do not allow messages before login.
                if logged_in_user is None:
                    send_json(conn, {
                        "status": "ERR",
                        "message": "You must LOGIN before sending messages."
                    })
                    continue

                text = request.get("text", "")

                if text.strip() == "":
                    send_json(conn, {
                        "status": "ERR",
                        "message": "Message cannot be empty."
                    })
                    continue

                print(f"[MESSAGE] {logged_in_user}: {text}")

                send_json(conn, {
                    "status": "OK",
                    "message": "Message received by server."
                })

            elif command == "FILE":
                # File transfer is also blocked until the user logs in.
                if logged_in_user is None:
                    send_json(conn, {
                        "status": "ERR",
                        "message": "You must LOGIN before sending files."
                    })
                    continue

                filename = request.get("filename", "")
                file_size = request.get("size", -1)

                filename = safe_filename(filename)

                if filename is None:
                    send_json(conn, {
                        "status": "ERR",
                        "message": "Invalid filename."
                    })
                    continue

                if not isinstance(file_size, int) or file_size < 0:
                    send_json(conn, {
                        "status": "ERR",
                        "message": "Invalid file size."
                    })
                    continue

                # Tell the client we are ready before it sends the file bytes.
                send_json(conn, {
                    "status": "READY",
                    "message": "Server is ready to receive file."
                })

                print(f"[FILE] Receiving {filename} from {logged_in_user} ({file_size} bytes)")

                # Now we receive the actual file data.
                file_data = recv_exact(conn, file_size)

                os.makedirs(RECEIVED_DIR, exist_ok=True)
                save_path = unique_path(RECEIVED_DIR, filename)

                with open(save_path, "wb") as file:
                    file.write(file_data)

                # Hash is not required, but it is useful for showing file integrity.
                file_hash = hashlib.sha256(file_data).hexdigest()

                print(f"[FILE RECEIVED] Saved as {save_path}")
                print(f"[FILE HASH] SHA256: {file_hash}")

                send_json(conn, {
                    "status": "OK",
                    "message": f"File received and saved as {os.path.basename(save_path)}.",
                    "sha256": file_hash
                })

            elif command == "QUIT":
                send_json(conn, {
                    "status": "OK",
                    "message": "Goodbye."
                })

                print(f"[QUIT] Client {addr} disconnected gracefully.")
                break

            else:
                send_json(conn, {
                    "status": "ERR",
                    "message": "Invalid command. Use LOGIN, MSG, FILE, or QUIT."
                })

    except ConnectionError as error:
        print(f"[ERROR] {error}")

    except OSError as error:
        print(f"[NETWORK ERROR] {error}")

    finally:
        conn.close()
        print(f"[CLOSED] Connection with {addr} closed.")


def main():
    valid_users = load_users(USERS_FILE)

    if not valid_users:
        print("[ERROR] No valid users loaded. Server cannot start.")
        return

    os.makedirs(RECEIVED_DIR, exist_ok=True)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # This lets us restart the server quickly without waiting for the port to fully clear.
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(1)

        print(f"[STARTED] Server listening on {HOST}:{PORT}")
        print("[WAITING] Waiting for clients...")

        while True:
            conn, addr = server_socket.accept()
            handle_client(conn, addr, valid_users)

            # After one client leaves, the server goes back to waiting.
            print("[WAITING] Waiting for another client...")

    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Server stopped manually.")

    except OSError as error:
        print(f"[SERVER ERROR] {error}")

    finally:
        server_socket.close()


if __name__ == "__main__":
    main()