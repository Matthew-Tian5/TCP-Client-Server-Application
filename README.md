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

| Command | Description |
|---------|-------------|
| `LOGIN username` | Authenticate with a username from `users.txt` |
| `MSG your message` | Send a text message (must be logged in) |
| `FILE path/to/file` | Upload a file (must be logged in) |
| `QUIT` | Disconnect from the server |

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

| Setting | Location | Default |
|---------|----------|---------|
| Server host | `server.py` → `HOST` | `0.0.0.0` |
| Server port | `server.py` → `PORT` | `5050` |
| Users file | `server.py` → `USERS_FILE` | `users.txt` |
| Upload directory | `server.py` → `RECEIVED_DIR` | `server_received_files` |

## License

See [LICENSE](LICENSE) for details.
