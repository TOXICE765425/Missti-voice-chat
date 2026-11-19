"""Voice-chat integration boundary.

This starter project deliberately does not pretend that Telegram Bot API can
receive live group-call audio. A working voice assistant needs a separately
authenticated MTProto client, a compatible PyTgCalls setup, incoming audio
stream handling, speech recognition, wake-word detection, and audio playback.

Do not put a Telegram session string in chat, GitHub, or Firebase. Keep it in
Render environment variables. The /join and /leave handlers currently explain
the setup state rather than falsely claiming to have joined a call.
"""

from .config import API_ID, API_HASH, SESSION_STRING

def voice_stack_configured() -> bool:
    return bool(API_ID and API_HASH and SESSION_STRING)

async def join_voice_chat(chat_id: int) -> tuple[bool, str]:
    if not voice_stack_configured():
        return False, (
            "Voice connection is not configured yet. Add API_ID, API_HASH "
            "and SESSION_STRING in Render environment variables."
        )
    return False, (
        "MTProto credentials are present, but live call audio handling is not "
        "enabled in this starter build. No voice chat was joined."
    )

async def leave_voice_chat(chat_id: int) -> tuple[bool, str]:
    return False, "No active voice-chat connection is managed by this starter build."
