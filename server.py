import os
import json
import random
import sqlite3
import threading
import asyncio
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pyngrok import ngrok, conf
from dotenv import load_dotenv

# --- 1. LOAD SECRETS ---
load_dotenv()
ROOM_PASSWORD = os.getenv("ROOM_PASSWORD", "admin")

# --- 2. DATABASE SETUP ---
conn = sqlite3.connect("chat.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
    "CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, sender TEXT, color TEXT, content TEXT)")
conn.commit()

app = FastAPI()

# --- 3. THE FRONTEND ---
html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Root Access Chat</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: monospace; background: #000; color: #0f0; padding: 20px; }
            #messages { height: 70vh; overflow-y: scroll; border: 1px solid #0f0; padding: 10px; margin-bottom: 10px; }
            input { background: #000; color: #0f0; border: 1px solid #0f0; padding: 10px; width: 70%; outline: none; }
            button { background: #0f0; color: #000; border: none; padding: 10px; cursor: pointer; font-weight: bold; }
            .msg-row { display: flex; align-items: center; margin-bottom: 8px; }
            .pfp { width: 35px; height: 35px; border-radius: 4px; margin-right: 12px; border: 1px solid #0f0; background: #111; }
            .msg-content { flex-grow: 1; }
            .ghost-msg { transition: opacity 0.5s ease-out; color: red; font-weight: bold; margin-bottom: 8px; }
        </style>
    </head>
    <body>
        <h2>>_ ROOT_ACCESS_CHAT</h2>
        <div id="messages"></div>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off" placeholder="Type command (/roll, /kick)..."/>
            <button>EXECUTE</button>
        </form>
        <script>
            var passkey = prompt("ENTER ROOT AUTHORIZATION KEY:");
            var protocol = window.location.protocol === "https:" ? "wss://" : "ws://";
            var ws = new WebSocket(protocol + location.host + "/ws?key=" + encodeURIComponent(passkey));
            
            ws.onmessage = function(event) {
                var data = JSON.parse(event.data);
                var messages = document.getElementById('messages');
                
                if (data.action === "clear") {
                    messages.innerHTML = "";
                    return; 
                }
                
                if (data.action === "ghost") {
                    var ghost = document.createElement('div');
                    ghost.className = 'ghost-msg';
                    ghost.innerHTML = `> ${data.text}`;
                    messages.appendChild(ghost);
                    messages.scrollTop = messages.scrollHeight; 
                    
                    setTimeout(() => {
                        ghost.style.opacity = "0";
                        setTimeout(() => ghost.remove(), 500);
                    }, 2000);
                    return;
                }
                
                var message = document.createElement('div');
                message.className = 'msg-row';
                
                if (data.sender === "SYSTEM") {
                    message.innerHTML = `<div class="msg-content"><b style="color: ${data.color}">[${data.sender}]</b>: ${data.text}</div>`;
                } else {
                    var avatarUrl = `https://api.dicebear.com/7.x/pixel-art/svg?seed=${encodeURIComponent(data.sender)}&backgroundColor=000000`;
                    message.innerHTML = `
                        <img src="${avatarUrl}" class="pfp" alt="PFP">
                        <div class="msg-content"><b style="color: ${data.color}">[${data.sender}]</b>: ${data.text}</div>
                    `;
                }
                
                messages.appendChild(message);
                messages.scrollTop = messages.scrollHeight; 
            };
            
            ws.onclose = function(event) {
                var messages = document.getElementById('messages');
                messages.innerHTML += "<br><b style='color: red;'>[SYSTEM]: Connection Severed.</b>";
            };
            
            function sendMessage(event) {
                var input = document.getElementById("messageText");
                if (input.value.trim() !== "") {
                    ws.send(input.value); 
                    input.value = '';
                }
                event.preventDefault();
            }
        </script>
    </body>
</html>
"""

# --- 4. IDENTITY GENERATOR ---
first_names = ["Ryota", "Kenji", "Haruki", "Yuto",
               "Takumi", "Hiroshi", "Akira", "Kaito", "Ren"]
last_names = ["Sato", "Takahashi", "Ito", "Watanabe",
              "Tanaka", "Suzuki", "Yamamoto", "Nakamura", "Kobayashi"]
colors = ["#FF5733", "#33FF57", "#3357FF",
          "#F333FF", "#33FFF3", "#FFD133", "#FF3333"]


def get_identity():
    return f"{random.choice(first_names)} {random.choice(last_names)}", random.choice(colors)

# --- 5. CONNECTION MANAGER & ADMIN STATE ---


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[WebSocket, dict] = {}
        self.admins: set = set()
        self.kicked_users: set = set()  # Tracks users who were forcefully booted

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        name, color = get_identity()
        self.active_connections[websocket] = {"name": name, "color": color}

        cursor.execute(
            "SELECT sender, color, content FROM history ORDER BY id ASC LIMIT 50")
        for row in cursor.fetchall():
            await websocket.send_text(json.dumps({"sender": row[0], "color": row[1], "text": row[2]}))

        await websocket.send_text(json.dumps({"sender": "SYSTEM", "color": "#ffffff", "text": f"You are {name} haha"}))
        return name, color

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            del self.active_connections[websocket]

    async def broadcast(self, sender: str, color: str, text: str, save: bool = True):
        if save and sender != "SYSTEM":
            cursor.execute(
                "INSERT INTO history (sender, color, content) VALUES (?, ?, ?)", (sender, color, text))
            conn.commit()

        payload = json.dumps({"sender": sender, "color": color, "text": text})
        for connection in self.active_connections:
            await connection.send_text(payload)

    async def grant_admin(self, target_name: str):
        self.admins.add(target_name)

    async def kick_user(self, target_name: str, kicker: str):
        """Finds the user's socket, flags them as kicked, and severs the connection."""
        target_ws = None
        for ws, info in self.active_connections.items():
            if info["name"] == target_name:
                target_ws = ws
                break

        if target_ws:
            self.kicked_users.add(target_name)
            # Send a silent kill screen before closing
            await target_ws.send_text(json.dumps({"action": "clear"}))
            await target_ws.close()
            await self.broadcast("SYSTEM", "#ff0000", f"👢 {target_name} was forcefully removed by {kicker}.", save=False)
            return True
        return False


manager = ConnectionManager()

# --- 6. SERVER TERMINAL (Background Thread) ---


def terminal_listener(loop):
    while True:
        cmd = input()
        if cmd.startswith("/give admin "):
            target = cmd.split("/give admin ", 1)[1].strip()
            asyncio.run_coroutine_threadsafe(manager.grant_admin(target), loop)
            print(f"[+] Silently granted admin to {target}")

        elif cmd.startswith("/kick "):
            target = cmd.split("/kick ", 1)[1].strip()
            # Send the kick command from the host
            asyncio.run_coroutine_threadsafe(
                manager.kick_user(target, "HOST"), loop)
            print(f"[+] Booted {target} from the server.")


@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_running_loop()
    threading.Thread(target=terminal_listener,
                     args=(loop,), daemon=True).start()

# --- 7. ROUTES ---


@app.get("/")
async def get():
    return HTMLResponse(html)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, key: str = None):
    if key != ROOM_PASSWORD:
        await websocket.accept()
        await websocket.send_text(json.dumps({"sender": "SYSTEM", "color": "#ff0000", "text": "ACCESS DENIED. INCORRECT KEY."}))
        await websocket.close()
        return

    name, color = await manager.connect(websocket)
    await manager.broadcast("SYSTEM", "#aaaaaa", f"⚠️ {name} has entered the chat.", save=False)

    try:
        while True:
            data = await websocket.receive_text()

            if data.startswith("/roll"):
                roll = random.randint(1, 100)
                await manager.broadcast("SYSTEM", "#ffcc00", f"🎲 {name} rolled a {roll}!", save=False)

            elif data.startswith("/clear"):
                if name in manager.admins:
                    cursor.execute("DELETE FROM history")
                    conn.commit()

                    kill_payload = json.dumps({"action": "clear"})
                    for connection in manager.active_connections:
                        await connection.send_text(kill_payload)

                    print(f"🗑️ [Database]: History purged silently by {name}")
                else:
                    await websocket.send_text(json.dumps({"action": "ghost", "text": "denied"}))

            elif data.startswith("/kick "):
                if name in manager.admins:
                    target = data.split("/kick ", 1)[1].strip()
                    success = await manager.kick_user(target, "an admin")
                    if not success:
                        # If they type the name wrong, silently tell them
                        await websocket.send_text(json.dumps({"action": "ghost", "text": "user not found"}))
                else:
                    await websocket.send_text(json.dumps({"action": "ghost", "text": "denied"}))

            else:
                print(f"📱 [{name}]: {data}")
                await manager.broadcast(name, color, data)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        # Check if they were kicked or just left normally
        if name in manager.kicked_users:
            manager.kicked_users.remove(name)  # Clean up the tracker
        else:
            await manager.broadcast("SYSTEM", "#aaaaaa", f"🔌 {name} disconnected.", save=False)

# --- 8. ONE-CLICK LAUNCHER ---
if __name__ == "__main__":
    print("Starting ngrok tunnel...")

    NGROK_TOKEN = os.getenv("NGROK_AUTH_TOKEN")
    if not NGROK_TOKEN:
        print("[-] Error: NGROK_AUTH_TOKEN not found in .env file!")
        exit(1)

    conf.get_default().auth_token = NGROK_TOKEN

    public_url = ngrok.connect(8000).public_url
    print("\n" + "="*60)
    print(f"🌍 GLOBAL NGROK TUNNEL LIVE: {public_url}")
    print(f"🔒 SERVER PASSWORD: {ROOM_PASSWORD}")
    print("="*60 + "\n")
    print("💻 HOST COMMANDS: '/give admin [Name]' | '/kick [Name]'")

    uvicorn.run(app, host="0.0.0.0", port=8000)
