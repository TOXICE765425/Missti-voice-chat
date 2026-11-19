from flask import Flask, jsonify
from threading import Thread
from .config import PORT

web_app = Flask(__name__)

@web_app.get("/")
def home():
    return jsonify({
        "name": "Missti AI VC",
        "status": "online",
        "note": "Telegram bot process health endpoint",
    })

@web_app.get("/health")
def health():
    return jsonify({"ok": True}), 200

def run_health_server():
    web_app.run(host="0.0.0.0", port=PORT, use_reloader=False)

def start_health_server():
    Thread(target=run_health_server, daemon=True).start()
