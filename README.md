# Missti AI VC — Updated voice pipeline build

This update replaces the old `voice_chat.py` placeholder with a PyTgCalls/Telethon
voice-chat integration, incoming audio recording pipeline, speech recognition,
wake-word check, AI response, and TTS playback.

## Important operating notes

- This uses a **Telegram user MTProto session** to access group-call media. Keep
  `SESSION_STRING` private; never commit it to GitHub or send it in chat.
- Add Missti to a test group, start a voice chat, tell members that audio is
  being processed, then run `/join`. Use `/leave` to stop processing.
- Incoming audio is processed in short chunks and not intentionally retained
  after leaving. Speech recognition uses Google's online recognition endpoint;
  availability, accuracy, and language support are not guaranteed.
- The voice pipeline is a practical integration, **not a claim of production
  validation**. It must be tested in a real Telegram group call. PyTgCalls,
  Telegram MTProto, network restrictions, and Render may affect call support.
- Render Free may sleep/restart and cannot guarantee uninterrupted voice calls.

## Render settings

Build command:
`pip install -r requirements.txt`

Start command:
`python -m app.main`

Health path:
`/health`

## Environment variables

Required for bot:
- `BOT_TOKEN`
- `BOT_USERNAME`
- `API_URL` (defaults to your supplied Missti API)
- `API_MODEL` (defaults to `gpt-5.2`)

Required for voice:
- `API_ID`
- `API_HASH`
- `SESSION_STRING` (Telethon StringSession for a dedicated test account)

Optional:
- `STT_LANGUAGE=hi-IN` (use `en-IN` for English recognition)
- `TTS_VOICE=hi-IN-SwaraNeural`
- `AUDIO_CHUNK_SECONDS=5`
- `OWNER_IDS`
- Firebase variables

## Commands

- `/start`
- `/help`
- `/status`
- `/join`
- `/leave`

The bot announces that voice processing is active before connecting. Do not
enable voice processing without informing the group participants.
