"""Telegram group voice assistant - minimal env, fuzzy wake word."""

import asyncio
import logging
import os
import re
import tempfile
import time
from collections import defaultdict

from .config import API_ID, API_HASH, SESSION_STRING
from .ai_engine import ask_ai

log = logging.getLogger("missti.voice")

# ===================== HARDCODED SETTINGS =====================
STT_LANGUAGE = "hi-IN"
TTS_VOICE = "hi-IN-SwaraNeural"
AUDIO_CHUNK_SECONDS = 4

# Wake word variants (STT galat sunne pe bhi detect ho)
WAKE_VARIANTS = [
    "missti", "misty", "misti", "missy", "mistie",
    "miss t", "mis t", "mi sti", "missti",
    "मिस्टी", "मिस्सी", "मिस्टी", "मिस्ती", "मिस्टी",
    "मिसटी", "मिस्टीजी", "हे मिस्टी", "hey missti",
]
# =============================================================

_manager = None


def _is_wake(text: str) -> bool:
    """Fuzzy check - exact word zaroori nahi."""
    if not text:
        return False
    t = text.casefold().strip()

    # Direct variant match
    for w in WAKE_VARIANTS:
        if w.casefold() in t:
            return True

    # Partial / noisy STT (e.g. "mis ti hello", "mssti", "mistii")
    cleaned = re.sub(r"[^a-zA-Z0-9\u0900-\u097F\s]", " ", t)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    tokens = cleaned.split()

    for tok in tokens:
        if len(tok) < 3:
            continue
        # close to "missti" / "misty"
        if tok.startswith("mis") or tok.startswith("mist") or tok.startswith("miss"):
            return True
        if "मिस्" in tok or "मिस" in tok:
            return True

    return False


def _remove_wake(text: str) -> str:
    t = text
    for w in WAKE_VARIANTS:
        t = re.sub(re.escape(w), "", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(mis+|mist+|miss+)\w*\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"(मिस्\w*|मिस\w*)", "", t)
    return t.strip(" ,:;.-")


class VoiceManager:
    def __init__(self):
        self.client = None
        self.calls = None
        self.active = {}
        self.buffers = defaultdict(bytearray)
        self.last_process = defaultdict(float)
        self.speaking = set()
        self.lock = asyncio.Lock()
        self._handler_registered = False

    async def initialize(self):
        if self.calls:
            return

        if not (API_ID and API_HASH and SESSION_STRING):
            raise RuntimeError("Set API_ID, API_HASH and SESSION_STRING only.")

        from pyrogram import Client
        from pytgcalls import PyTgCalls, filters
        from pytgcalls.types import Device, Direction, StreamFrames

        self.client = Client(
            name="missti_vc",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=SESSION_STRING,
            in_memory=True,
        )
        await self.client.start()
        me = await self.client.get_me()
        if not me:
            await self.client.stop()
            self.client = None
            raise RuntimeError("SESSION_STRING invalid / not authorized.")

        self.calls = PyTgCalls(self.client)
        await self.calls.start()

        if not self._handler_registered:
            @self.calls.on_update(
                filters.stream_frame(Direction.INCOMING, Device.MICROPHONE)
            )
            async def _on_audio_frames(_: PyTgCalls, update: StreamFrames):
                await self._handle_frames(update)
            self._handler_registered = True

        log.info("Pyrogram + PyTgCalls ready (user_id=%s).", me.id)

    async def _handle_frames(self, update):
        chat_id = update.chat_id
        if chat_id not in self.active or chat_id in self.speaking:
            return

        for frame_data in update.frames:
            if frame_data.frame:
                self.buffers[chat_id].extend(frame_data.frame)

        now = time.time()
        if now - self.last_process[chat_id] < AUDIO_CHUNK_SECONDS:
            return
        self.last_process[chat_id] = now

        buf = self.buffers[chat_id]
        # ~1.5 sec minimum
        if len(buf) < 48000 * 2 * 2 * 1.5:
            return

        chunk = bytes(buf)
        self.buffers[chat_id].clear()

        try:
            transcript = await asyncio.to_thread(self._transcribe, chunk)
            if not transcript:
                return

            log.info("Transcript [%s]: %s", chat_id, transcript)

            if not _is_wake(transcript):
                return

            question = _remove_wake(transcript) or "Say hello briefly."
            await self._answer_in_voice(chat_id, question)
        except Exception:
            log.exception("Voice processing error chat %s", chat_id)

    async def join(self, chat_id: int):
        async with self.lock:
            await self.initialize()
            if chat_id in self.active:
                return True, "Missti already connected."

            from pytgcalls.types import (
                RecordStream, GroupCallConfig, MediaStream, ExternalMedia
            )
            from pytgcalls.types.raw import AudioParameters

            params = AudioParameters(bitrate=48000, channels=2)

            await self.calls.play(
                chat_id,
                MediaStream(ExternalMedia.AUDIO, params),
                GroupCallConfig(auto_start=True),
            )
            await self.calls.record(chat_id, RecordStream(True, params))

            self.active[chat_id] = {"joined_at": time.time()}
            self.buffers[chat_id].clear()
            self.last_process[chat_id] = 0.0

            log.info("Joined voice chat %s", chat_id)
            return True, "❤️ Missti connected. Bol: Missti + sawal"

    async def leave(self, chat_id: int):
        async with self.lock:
            if chat_id not in self.active:
                return False, "Not connected."

            self.active.pop(chat_id, None)
            self.buffers.pop(chat_id, None)
            self.last_process.pop(chat_id, None)
            self.speaking.discard(chat_id)

            try:
                await self.calls.leave_call(chat_id)
            except Exception as e:
                log.warning("Leave issue %s: %s", chat_id, e)

            return True, "Missti left the voice chat."

    async def shutdown(self):
        for cid in list(self.active):
            try:
                await self.leave(cid)
            except Exception:
                pass
        if self.calls:
            try:
                await self.calls.stop()
            except Exception:
                pass
        if self.client:
            try:
                await self.client.stop()
            except Exception:
                pass
        self.calls = None
        self.client = None
        self._handler_registered = False

    def _transcribe(self, pcm: bytes) -> str:
        import speech_recognition as sr
        import audioop

        try:
            mono = audioop.tomono(pcm, 2, 0.5, 0.5)
            mono16 = audioop.ratecv(mono, 2, 1, 48000, 16000, None)[0]
            r = sr.Recognizer()
            audio = sr.AudioData(mono16, 16000, 2)
            return r.recognize_google(audio, language=STT_LANGUAGE)
        except Exception:
            return ""

    async def _answer_in_voice(self, chat_id: int, prompt: str):
        try:
            answer = await asyncio.to_thread(ask_ai, prompt)
            if not answer:
                answer = "Sorry, samajh nahi aaya."
            await self._speak(chat_id, answer)
        except Exception:
            log.exception("Answer failed chat %s", chat_id)

    async def _speak(self, chat_id: int, text: str):
        import edge_tts
        import subprocess
        import imageio_ffmpeg
        from pytgcalls.types import Device, ExternalMedia, MediaStream
        from pytgcalls.types.raw import AudioParameters

        self.speaking.add(chat_id)
        try:
            with tempfile.TemporaryDirectory(prefix="missti_") as tmp:
                mp3 = os.path.join(tmp, "r.mp3")
                raw = os.path.join(tmp, "r.raw")

                await edge_tts.Communicate(text[:1200], TTS_VOICE).save(mp3)

                subprocess.run(
                    [
                        imageio_ffmpeg.get_ffmpeg_exe(),
                        "-y", "-i", mp3,
                        "-f", "s16le", "-acodec", "pcm_s16le",
                        "-ac", "2", "-ar", "48000", raw,
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                try:
                    await self.calls.play(
                        chat_id,
                        MediaStream(
                            ExternalMedia.AUDIO,
                            AudioParameters(bitrate=48000, channels=2),
                        ),
                    )
                except Exception:
                    pass

                frame_size = 48000 * 2 * 2 // 50  # 20ms
                with open(raw, "rb") as f:
                    while True:
                        frame = f.read(frame_size)
                        if not frame:
                            break
                        if len(frame) < frame_size:
                            frame += b"\x00" * (frame_size - len(frame))
                        await self.calls.send_frame(chat_id, Device.MICROPHONE, frame)
                        await asyncio.sleep(0.02)
        finally:
            self.speaking.discard(chat_id)


async def join_voice_chat(chat_id: int):
    global _manager
    if _manager is None:
        _manager = VoiceManager()
    try:
        return await _manager.join(chat_id)
    except Exception as e:
        log.exception("Join failed")
        return False, f"Voice connection failed: {type(e).__name__}: {e}"


async def leave_voice_chat(chat_id: int):
    global _manager
    if _manager is None:
        return False, "No active connection."
    try:
        return await _manager.leave(chat_id)
    except Exception as e:
        log.exception("Leave failed")
        return False, f"Leave failed: {e}"


def voice_status(chat_id: int) -> bool:
    return bool(_manager and chat_id in _manager.active)


async def shutdown_voice():
    global _manager
    if _manager:
        await _manager.shutdown()
        _manager = None
