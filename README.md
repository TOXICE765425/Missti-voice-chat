# Missti AI VC

Telegram bot starter project with a welcome menu, multiple owner links, Firebase user storage, GPT-5.2 API text replies, and a Render health endpoint.

## Folder layout

```text
Missti-AI-VC/
├── app/                 # All Python source files are kept here
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── ai_engine.py
│   ├── voice_chat.py
│   └── keep_alive.py
├── requirements.txt
├── render.yaml
├── Procfile
├── .env.example
└── README.md
```

## Important voice-chat limitation

This is a starter bot, not a completed live voice-chat assistant. The Telegram Bot API does not provide live group-call audio access. The `voice_chat.py` file is an explicit integration boundary: it does not claim to join calls. A complete voice assistant still needs a tested MTProto/PyTgCalls call connection, incoming audio decoding, speech recognition, wake-word detection, TTS generation, and outgoing audio streaming. Do not deploy this expecting `/join` to already work.

## Environment variables

Set these in Render:

- `BOT_TOKEN`: Telegram bot token from BotFather.
- `BOT_USERNAME`: bot username without `@`.
- `API_URL`: `https://misstupapachataiapi.vercel.app/api/chat`
- `API_MODEL`: `gpt-5.2`
- `OWNER_IDS`: comma-separated numeric Telegram user IDs, e.g. `111111111,222222222`.
- `SUPPORT_LINK`: `https://t.me/misstu_pro`
- `FIREBASE_DATABASE_URL`: Firebase Realtime Database URL.
- `FIREBASE_CREDENTIALS_JSON`: service-account JSON as one-line JSON text.
- `API_ID`, `API_HASH`, `SESSION_STRING`: reserved for the separate MTProto voice engine. Keep session string secret.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill .env values, then:
python -m app.main
```

## Render

Create a new Web Service from this repository. Render can use `render.yaml`. Add all required environment variables in the Render dashboard. The `/health` endpoint is for service health checks and UptimeRobot monitoring.

UptimeRobot pings do not guarantee that a Render Free service will remain awake or that a voice connection will remain uninterrupted.

## Welcome menu

- Add To Your Group: opens Telegram's add-to-group flow.
- Help & Commands: shows available commands.
- Support: opens `@misstu_pro`.
- Boss: displays configured owner profile links.

The user's own profile photo is used as the welcome image when Telegram permits the bot to retrieve it; otherwise the bot sends a text welcome.
