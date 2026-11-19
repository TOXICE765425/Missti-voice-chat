import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lstrip("@")
API_URL = os.getenv("API_URL", "https://misstupapachataiapi.vercel.app/api/chat")
API_MODEL = os.getenv("API_MODEL", "gpt-5.2")
SUPPORT_LINK = os.getenv("SUPPORT_LINK", "https://t.me/misstu_pro")
WAKE_WORD = os.getenv("WAKE_WORD", "Missti")
PORT = int(os.getenv("PORT", "10000"))

OWNER_IDS = [
    int(value.strip())
    for value in os.getenv("OWNER_IDS", "").split(",")
    if value.strip().isdigit()
]

FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL", "")
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON", "")

API_ID = int(os.getenv("API_ID", "0") or 0)
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")

STT_LANGUAGE = os.getenv("STT_LANGUAGE", "hi-IN")
TTS_VOICE = os.getenv("TTS_VOICE", "hi-IN-SwaraNeural")
AUDIO_CHUNK_SECONDS = max(3, min(8, int(os.getenv("AUDIO_CHUNK_SECONDS", "5"))))
