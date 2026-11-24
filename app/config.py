import os

# ========== ONLY FROM ENVIRONMENT ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_ID = int(os.getenv("API_ID", "0") or 0)
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")

OWNER_IDS = [
    int(x.strip())
    for x in os.getenv("OWNER_IDS", "").split(",")
    if x.strip().isdigit()
]

FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL", "")
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON", "")

# ========== HARDCODED ==========
API_URL = "https://misstupapachataiapi.vercel.app/api/chat"
API_MODEL = "gpt-5.2"
SUPPORT_LINK = "https://t.me/misstu_pro"
PORT = 10000
WAKE_WORD = "Missti"
STT_LANGUAGE = "hi-IN"
TTS_VOICE = "hi-IN-SwaraNeural"
AUDIO_CHUNK_SECONDS = 4
