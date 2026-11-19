import json
import firebase_admin
from firebase_admin import credentials, db
from .config import FIREBASE_DATABASE_URL, FIREBASE_CREDENTIALS_JSON

_app = None

def initialize_firebase():
    global _app
    if _app is not None:
        return _app
    if not FIREBASE_DATABASE_URL or not FIREBASE_CREDENTIALS_JSON:
        print("Firebase not configured; database features are disabled.")
        return None
    try:
        try:
            credential_data = json.loads(FIREBASE_CREDENTIALS_JSON)
        except json.JSONDecodeError:
            with open(FIREBASE_CREDENTIALS_JSON, "r", encoding="utf-8") as handle:
                credential_data = json.load(handle)
        cred = credentials.Certificate(credential_data)
        _app = firebase_admin.initialize_app(
            cred, {"databaseURL": FIREBASE_DATABASE_URL}
        )
        print("Firebase connected.")
        return _app
    except Exception as exc:
        print(f"Firebase initialization failed: {exc}")
        return None

def save_user(user):
    if initialize_firebase() is None:
        return
    try:
        db.reference(f"users/{user.id}").update({
            "name": user.full_name or "",
            "username": user.username or "",
            "userid": user.id,
        })
    except Exception as exc:
        print(f"Firebase save failed: {exc}")

def save_event(group_id, event, data=None):
    if initialize_firebase() is None:
        return
    try:
        db.reference(f"groups/{group_id}/events").push({
            "event": event,
            "data": data or {},
        })
    except Exception as exc:
        print(f"Firebase event save failed: {exc}")
