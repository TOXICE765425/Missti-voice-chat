"""Telegram group voice assistant.

Audio is processed only after /join and after the group is informed.
Uses a Pyrogram user session for MTProto voice-chat access and PyTgCalls
for call media. Never expose SESSION_STRING in chat, GitHub, or logs.
"""
import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path

from .config import (
    API_ID, API_HASH, SESSION_STRING, WAKE_WORD,
    STT_LANGUAGE, TTS_VOICE, AUDIO_CHUNK_SECONDS,
)
from .ai_engine import ask_ai

log = logging.getLogger("missti.voice")

_manager = None


class VoiceManager:
    def __init__(self):
        self.client = None
        self.calls = None
        self.active = {}
        self.tasks = {}
        self.lock = asyncio.Lock()

    async def initialize(self):
        if self.calls:
            return
        if not (API_ID and API_HASH and SESSION_STRING):
            raise RuntimeError("Set API_ID, API_HASH and SESSION_STRING in Render.")
        from pyrogram import Client
        from pytgcalls import PyTgCalls

        # Pyrogram string session (in-memory). Do not use Telethon StringSession here.
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
            raise RuntimeError("SESSION_STRING is not authorized. Generate a fresh Pyrogram user session.")
        self.calls = PyTgCalls(self.client)
        await self.calls.start()
        log.info("Pyrogram MTProto client and PyTgCalls initialized (user_id=%s).", me.id)

    async def join(self, chat_id: int):
        async with self.lock:
            await self.initialize()
            if chat_id in self.active:
                return True, "Missti is already connected to this voice chat."

            # PyTgCalls RecordStream writes the incoming call mix to a local
            # raw audio stream. No permanent recordings are retained.
            from pytgcalls.types import RecordStream, GroupCallConfig
            raw_path = Path(tempfile.gettempdir()) / f"missti_{abs(chat_id)}.raw"
            try:
                raw_path.unlink(missing_ok=True)
            except Exception:
                pass

            await self.calls.record(
                chat_id,
                RecordStream(audio=str(raw_path)),
                GroupCallConfig(auto_start=True),
            )
            self.active[chat_id] = {"raw": raw_path, "offset": 0, "buffer": bytearray()}
            task = asyncio.create_task(self._listen_loop(chat_id))
            self.tasks[chat_id] = task
            log.info("Voice assistant joined chat %s", chat_id)
            return True, (
                "❤️ Missti voice assistant connected. Audio processing is active "
                "only while joined. Say 'Missti' followed by your question."
            )

    async def leave(self, chat_id: int):
        async with self.lock:
            if chat_id not in self.active:
                return False, "Missti is not connected to this voice chat."
            task = self.tasks.pop(chat_id, None)
            if task:
                task.cancel()
            state = self.active.pop(chat_id, None)
            try:
                await self.calls.leave_call(chat_id)
            except Exception as exc:
                log.warning("Leave call issue for %s: %s", chat_id, exc)
            if state:
                try:
                    state["raw"].unlink(missing_ok=True)
                except Exception:
                    pass
            return True, "Missti has left the voice chat."

    async def shutdown(self):
        for chat_id in list(self.active):
            try:
                await self.leave(chat_id)
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

    async def _listen_loop(self, chat_id: int):
        state = self.active[chat_id]
        raw_path = state["raw"]
        # 48 kHz, stereo, signed 16-bit PCM = 192,000 bytes/sec.
        bytes_per_second = 48000 * 2 * 2
        chunk_bytes = bytes_per_second * AUDIO_CHUNK_SECONDS
        while chat_id in self.active:
            await asyncio.sleep(1)
            try:
                if not raw_path.exists():
                    continue
                size = raw_path.stat().st_size
                if size <= state["offset"] or size - state["offset"] < chunk_bytes:
                    continue
                with raw_path.open("rb") as stream:
                    stream.seek(state["offset"])
                    data = stream.read(chunk_bytes)
                if len(data) < chunk_bytes:
                    continue
                state["offset"] += len(data)
                transcript = await asyncio.to_thread(self._transcribe, data)
                if not transcript:
                    continue
                log.info("Voice transcript detected in chat %s", chat_id)
                if WAKE_WORD.casefold() not in transcript.casefold():
                    continue
                question = self._remove_wake_word(transcript)
                if not question:
                    question = "Say hello briefly."
                await self._answer_in_voice(chat_id, question)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Voice processing error for chat %s", chat_id)

    def _transcribe(self, pcm: bytes) -> str:
        """Convert one short PCM chunk and transcribe it; no audio is saved."""
        import speech_recognition as sr
        import wave
        import audioop

        mono = audioop.tomono(pcm, 2, 0.5, 0.5)
        mono_16k = audioop.ratecv(mono, 2, 1, 48000, 16000, None)[0]
        recognizer = sr.Recognizer()
        audio = sr.AudioData(mono_16k, 16000, 2)
        try:
            return recognizer.recognize_google(audio, language=STT_LANGUAGE)
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as exc:
            log.warning("Speech recognition service unavailable: %s", exc)
            return ""

    @staticmethod
    def _remove_wake_word(text: str) -> str:
        import re
        return re.sub(re.escape(WAKE_WORD), "", text, flags=re.IGNORECASE).strip(" ,:;.-")

    async def _answer_in_voice(self, chat_id: int, prompt: str):
        answer = await asyncio.to_thread(ask_ai, prompt)
        await self._speak(chat_id, answer)

    async def _speak(self, chat_id: int, text: str):
        import edge_tts
        import subprocess
        import imageio_ffmpeg
        from pytgcalls.types import Device, ExternalMedia, MediaStream
        from pytgcalls.types.raw import AudioParameters

        with tempfile.TemporaryDirectory(prefix="missti_tts_") as tmp:
            mp3 = os.path.join(tmp, "reply.mp3")
            raw = os.path.join(tmp, "reply.raw")
            communicate = edge_tts.Communicate(text[:1200], TTS_VOICE)
            await communicate.save(mp3)
            subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", mp3, "-f", "s16le",
                    "-acodec", "pcm_s16le", "-ac", "2", "-ar", "48000", raw,
                ],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            # Ensure an audio stream exists, then feed PCM frames to the call.
            await self.calls.play(
                chat_id,
                MediaStream(
                    ExternalMedia.AUDIO,
                    AudioParameters(bitrate=48000, channels=2),
                ),
            )
            frame_size = 48000 * 2 * 2 // 50  # 20 ms
            with open(raw, "rb") as stream:
                while True:
                    frame = stream.read(frame_size)
                    if not frame:
                        break
                    if len(frame) < frame_size:
                        frame += b"\x00" * (frame_size - len(frame))
                    await self.calls.send_frame(chat_id, Device.MICROPHONE, frame)
                    await asyncio.sleep(0.02)


async def join_voice_chat(chat_id: int):
    global _manager
    if _manager is None:
        _manager = VoiceManager()
    try:
        return await _manager.join(chat_id)
    except Exception as exc:
        log.exception("Could not join voice chat")
        return False, f"Voice connection failed: {type(exc).__name__}: {exc}"


async def leave_voice_chat(chat_id: int):
    global _manager
    if _manager is None:
        return False, "No active voice-chat connection."
    try:
        return await _manager.leave(chat_id)
    except Exception as exc:
        log.exception("Could not leave voice chat")
        return False, f"Could not leave voice chat: {exc}"


def voice_status(chat_id: int) -> bool:
    return bool(_manager and chat_id in _manager.active)


async def shutdown_voice():
    global _manager
    if _manager:
        await _manager.shutdown()
        _manager = None
