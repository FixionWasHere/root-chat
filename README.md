# >_ Root Access Chat

A secure, real-time, terminal-themed chatroom built with Python, FastAPI, and WebSockets. 

Unlike traditional chat apps that require deploying backend code to a cloud provider (like AWS or Heroku), **Root Access Chat** is designed to run entirely on the host's local machine. It dynamically generates a secure global tunnel, allowing anyone in the world to connect to your local terminal via their web browser.

## 🧠 How It Works (The Architecture)

1. **The Server Initialization:** When `server.py` is executed, it simultaneously spins up a local SQLite database, an asynchronous FastAPI web server, and a background terminal-listening thread.
2. **The Global Tunnel:** The script uses the `pyngrok` wrapper to securely expose the local port (8000) to the public internet, generating a live `https://` URL on the fly.
3. **The Handshake:** When a user visits the URL, the server serves a single-page HTML/JS frontend. The JavaScript prompts the user for the room password and attempts to open a `wss://` (Secure WebSocket) connection.
4. **The Bouncer:** The Python backend intercepts the WebSocket request, verifies the password against a hidden `.env` file, and either rejects the connection or accepts it, assigning the user a dynamic identity.
5. **The Broadcast:** Messages sent from the browser are routed through the ngrok tunnel to the Python server, logged into the database, and instantly broadcasted back out to all active WebSocket connections.

## 🚀 Key Features

### 🛡️ Security & Access
* **Root Authorization:** The server is locked behind a custom password stored safely in local environment variables. Unauthorized connection attempts are instantly severed.
* **Ngrok Integration:** No complex router port-forwarding is required. The app handles its own secure internet tunneling.

### ⚡ Real-Time Engine
* **Bidirectional WebSockets:** True real-time communication with zero polling latency.
* **Database Persistence:** Chat history is continuously logged to a local `chat.db` file. When a new user connects, the server automatically queries and loads the last 50 messages so they are never staring at an empty screen.

### 🎭 UI / UX
* **Dynamic Pixel-Art Avatars:** Integrates with the DiceBear API. Instead of requiring users to upload images, the server uses their assigned Japanese alias as a cryptographic seed to generate a permanently unique, 8-bit avatar on the fly.
* **Terminal Aesthetic:** A custom, responsive CSS layout designed to mimic a high-contrast hacker terminal, optimized for both desktop and mobile browsers.

### 👑 Stealth Admin Controls
The host terminal runs a background thread that listens for keyboard input without interrupting the asynchronous web server, enabling "God Mode" commands:
* **Silent Promotion:** Typing `/give admin [Name]` in the host terminal grants that user root privileges without alerting the rest of the lobby.
* **The Nuke Command:** Admins can type `/clear` in the chat to instantly wipe the SQLite database and send a hidden JSON signal that forcefully clears the screen of every connected device.
* **Ghost Messages:** If a non-admin attempts to use a root command, the server routes a self-destructing, fading error message specifically to their screen, leaving zero trace in the global chat.
* **Force Boot:** The host can use `/kick [Name]` to target a specific WebSocket, sever the connection, and lock their browser screen black.

## 🛠️ Tech Stack
* **Backend:** Python, FastAPI, Uvicorn, SQLite3, asyncio, threading
* **Networking:** WebSockets, Pyngrok (TCP Tunneling)
* **Frontend:** HTML5, CSS3, Vanilla JavaScript 
* **Security:** python-dotenv

## ⚙️ How to Run Locally

1. Clone the repository.
2. Install the required dependencies: 
   ```bash
   pip install fastapi uvicorn websockets pyngrok python-dotenv
3. Create a .env file in the root directory and add your credentials:
   ```bash
   NGROK_AUTH_TOKEN=your_ngrok_token_here
   ROOM_PASSWORD=your_custom_password
4.Start the server, enter this in your terminal 
  ```bash
  python server.py



