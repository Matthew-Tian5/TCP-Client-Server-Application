# TCP Client-Server Application

A Python TCP client-server application with JSON-based messaging. Clients authenticate with a username, send text messages, and transfer files to the server. Built for **CP372 Assignment 1**.

## Features

- **Login** — Username validated against `users.txt`
- **Messages** — Send text to the server (requires login)
- **File transfer** — Upload files with size metadata; server saves them and returns a SHA-256 hash
- **Graceful disconnect** — `QUIT` closes the session cleanly

The server handles one client at a time. Received files are stored in `server_received_files/` with automatic renaming if a filename already exists.

## Requirements

- Python 3.6+ (stdlib only — no external packages)

## Project structure

```
TCP-Client-Server-Application/
├── server.py          # TCP server
├── client.py          # Interactive TCP client
├── users.txt          # Allowed usernames (one per line)
├── server_received_files/   # Created at runtime for uploaded files
└── README.md
```

## Setup

1. Clone or download this repository.
2. Edit `users.txt` and add one valid username per line (empty lines are ignored).

Example `users.txt`:

```
Alyssa
Melanie
Mathew
Ali
```

## Running the application

### 1. Start the server

```bash
python server.py
```

The server listens on `0.0.0.0:5050` by default (all interfaces). It will not start if `users.txt` is missing or empty.

### 2. Start the client

In a separate terminal:

```bash
python client.py
```

When prompted, enter the server IP (default `127.0.0.1`) and port (default `5050`).

## Client commands

| Command             | Description                                   |
| ------------------- | --------------------------------------------- |
| `LOGIN username`    | Authenticate with a username from `users.txt` |
| `MSG your message`  | Send a text message (must be logged in)       |
| `FILE path/to/file` | Upload a file (must be logged in)             |
| `QUIT`              | Disconnect from the server                    |

## Protocol overview

Control messages are newline-terminated JSON objects. File uploads use a two-step flow:

1. Client sends `{"cmd": "FILE", "filename": "...", "size": N}`
2. Server replies with `{"status": "READY", ...}`, then the client sends `N` raw bytes
3. Server saves the file and replies with `{"status": "OK", "sha256": "..."}`

Other commands use a single request/response pair, for example:

```json
{"cmd": "LOGIN", "user": "Ali"}
{"cmd": "MSG", "text": "Hello, server!"}
{"cmd": "QUIT"}
```

Server responses include a `status` field (`OK`, `ERR`, or `READY`) and a `message` string.

## Client implementation walkthrough

The client is organised so that each protocol command maps to a small handler function. The `main()` dispatch loop reads a line of input, splits it into a command and an argument, and calls the matching handler.

### Where each command is implemented

| Command | Function                   | Lines in `client.py` | Summary                                                                                                      |
| ------- | -------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------ |
| `LOGIN` | `do_login()`               | 90–100               | Sends `{"cmd": "LOGIN", "user": ...}` and prints the reply                                                   |
| `MSG`   | `do_msg()`                 | 102–111              | Pre-checks for empty input, sends `{"cmd": "MSG", "text": ...}`, prints the reply                            |
| `FILE`  | `do_file()`                | 113–170              | Reads the local file, sends the header, waits for `READY`, sends bytes, prints the final reply with `sha256` |
| `QUIT`  | `do_quit()`                | 172–184              | Sends `{"cmd": "QUIT"}`, reads `Goodbye`, signals the main loop to exit                                      |
| `HELP`  | handled inline in `main()` | 268                  | Local-only; prints the command list without contacting the server                                            |

Unknown commands are also caught inside `main()` so they never reach the server.

### Transport helpers (shared across every command)

These three functions are how the client speaks the protocol. Every handler goes through them.

- **`send_json()`** (line 24) — serialises a Python dict as JSON, appends `\n`, and calls `sock.sendall()`. The newline is what tells the server where one message ends and the next begins.
- **`recv_line()`** (line 33) — reads from the socket one byte at a time until a `\n` is seen, then returns the line without the newline. Returns `None` if the server closed the connection. Matches the server's own `recv_line()` exactly so both sides agree on framing.
- **`recv_json()`** (line 60) — calls `recv_line()` and parses the result with `json.loads()`. This is what every handler calls to read a server reply.

### The `FILE` two-step (the tricky one)

`FILE` is the only command that needs more than one round-trip, and it is also the easiest one to break. The flow inside `do_file()` is:

1. **Local validation first** — `os.path.isfile()` and a `try`/`except OSError` on `open()` so the client never sends a header for a file it cannot read.
2. **Send the header** — `{"cmd": "FILE", "filename": ..., "size": ...}` via `send_json()`.
3. **Read the first reply** with `recv_json()`. The server replies `READY` if the header looks valid, or `ERR` if the filename is empty or the size is not a non-negative integer.
4. **Check the status before sending bytes.** If the status is anything other than `READY`, return immediately without sending data. This matters — sending raw bytes after an `ERR` would desync the stream, because the server would try to parse those bytes as the next JSON command.
5. **Send the raw file bytes** in one `sock.sendall(data)` call.
6. **Read the final reply**, which contains the `sha256` hash the server computed over the received bytes. The client prints it as a `[SHA256] ...` line so the user can compare it against the local file.

### Connection setup

`main()` (line 219) does three things before entering the dispatch loop:

1. Calls `prompt_host_and_port()` to read the server address from the user (defaults to `127.0.0.1:5050`, or reads from `sys.argv` if two extra command-line args are given).
2. Calls `sock.connect()` and exits cleanly with a friendly message if the server is not reachable.
3. Sets `sock.settimeout(60)` so the client cannot hang forever if the server stops responding mid-conversation. The timeout raises `socket.timeout`, which is a subclass of `OSError` and is caught by the main loop's general error handler.

### Error handling layers

Errors are caught at the layer where they happen, so one bad input never kills the client:

- **Local user errors** (file not found, empty argument, unknown command, bad CLI port) are handled inside the handler or in `prompt_host_and_port()` and never reach the server.
- **Server-side errors** come back as `{"status": "ERR", ...}` and are printed by `print_response()` in a consistent `[ERR] message` format.
- **Connection errors** (server closed, timeout, broken pipe) are caught in the `except (ConnectionError, OSError)` block inside the `main()` loop, which prints the error and exits the loop cleanly.
- **Bad JSON from the server** raises `ValueError` from `recv_json()`, which is caught in the same loop and skipped without breaking the connection.
- **Ctrl+C** is caught at the top level — the client attempts a final `QUIT` and then closes the socket in the `finally` block.

## Example session

**Server terminal:**

```text
[STARTED] Server listening on 0.0.0.0:5050
[WAITING] Waiting for clients...
[CONNECTED] Client connected from ('127.0.0.1', 54321)
[LOGIN] Ali logged in from ('127.0.0.1', 54321)
[MESSAGE] Ali: Hello from the client
[FILE] Receiving report.pdf from Ali (1024 bytes)
[FILE RECEIVED] Saved as server_received_files/report.pdf
[QUIT] Client ('127.0.0.1', 54321) disconnected gracefully.
```

**Client terminal:**

```text
> LOGIN Ali
[OK] Welcome, Ali.
> MSG Hello from the client
[OK] Message received by server.
> FILE ./report.pdf
[READY] Server is ready to receive file.
[OK] File received and saved as report.pdf.
[SHA256] abc123...
> QUIT
[OK] Goodbye.
```

## Configuration

| Setting          | Location                     | Default                 |
| ---------------- | ---------------------------- | ----------------------- |
| Server host      | `server.py` → `HOST`         | `0.0.0.0`               |
| Server port      | `server.py` → `PORT`         | `5050`                  |
| Users file       | `server.py` → `USERS_FILE`   | `users.txt`             |
| Upload directory | `server.py` → `RECEIVED_DIR` | `server_received_files` |

## License

See [LICENSE](LICENSE) for details.
