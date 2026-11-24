"""Telegram group voice assistant.

Uses Pyrogram user session + PyTgCalls.
Listens via incoming stream frames (not file-based recording).
"""

import asyncio
import logging
import os
import re
import tempfile
import time
from collections import defaultdict
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
        self.active = {}          # chat_id -> state
        self.buffers = defaultdict(bytearray)
        self.last_process = defaultdict(float)
        self.speaking = set()     # chats where we are currently speaking
        self.lock = asyncio.Lock()
        self._handler_registered = False

    async def initialize(self):
        if self.calls:
            return

        if not (API_ID and API_HASH and SESSION_STRING):
            raise RuntimeError("Set API_ID, API_HASH and SESSION_STRING in Render.")

        from pyrogram import Client
        from pytgcalls import PyTgCalls, filters
        from pytgcalls.types import Device, Direction, StreamFrames
        from pytgcalls.types.raw import AudioParameters

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

        # Register incoming audio frame handler only once
        if not self._handler_registered:
            @self.calls.on_update(
                filters.stream_frame(Direction.INCOMING, Device.MICROPHONE)
            )
            async def _on_audio_frames(_: PyTgCalls, update: StreamFrames):
                await self._handle_frames(update)

            self._handler_registered = True

        log.info("Pyrogram + PyTgCalls initialized (user_id=%s).", me.id)

    async def _handle_frames(self, update):
        chat_id = update.chat_id
        if chat_id not in self.active:
            return
        if chat_id in self.speaking:
            return  # ignore while we are speaking

        for frame_data in update.frames:
            if frame_data.frame:
                self.buffers[chat_id].extend(frame_data.frame)

        # Process every AUDIO_CHUNK_SECONDS
        now = time.time()
        if now - self.last_process[chat_id] < max(2.0, AUDIO_CHUNK_SECONDS):
            return
        self.last_process[chat_id] = now

        buf = self.buffers[chat_id]
        if len(buf) < 48000 * 2 * 2 * 1.5:  # at least ~1.5 sec
            return

        # Take a chunk and clear buffer
        chunk = bytes(buf)
        self.buffers[chat_id].clear()

        try:
            transcript = await asyncio.to_thread(self._transcribe, chunk)
            if not transcript:
                return
            log.info("Voice transcript [%s]: %s", chat_id, transcript)

            if WAKE_WORD.casefold() not in transcript.casefold():
                return

            question = self._remove_wake_word(transcript)
            if not question:
                question = "Say hello briefly."

            await self._answer_in_voice(chat_id, question)
        except Exception:
            log.exception("Voice processing error for chat %s", chat_id)

    async def join(self, chat_id: int):
        async with self.lock:
            await self.initialize()
            if chat_id in self.active:
                return True, "Missti is already connected to this voice chat."

            from pytgcalls.types import RecordStream, GroupCallConfig, MediaStream, ExternalMedia
            from pytgcalls.types.raw import AudioParameters

            audio_params = AudioParameters(bitrate=48000, channels=2)

            # Start external audio stream (needed for later speaking)
            await self.calls.play(
                chat_id,
                MediaStream(ExternalMedia.AUDIO, audio_params),
                GroupCallConfig(auto_start=True),
            )

            # Start recording incoming audio as frames
            await self.calls.record(
                chat_id,
                RecordStream(True, audio_params),
            )

            self.active[chat_id] = {"joined_at": time.time()}
            self.buffers[chat_id].clear()
            self.last_process[chat_id] = 0.0

            log.info("Voice assistant joined chat %s", chat_id)
            return True, (
                "❤️ Missti voice assistant connected.\n"
                "Say **Missti** followed by your question."
            )

    async def leave(self, chat_id: int):
        async with self.lock:
            if chat_id not in self.active:
                return False, "Missti is not connected to this voice chat."

            self.active.pop(chat_id, None)
            self.buffers.pop(chat_id, None)
            self.last_process.pop(chat_id, None)
            self.speaking.discard(chat_id)

            try:
                await self.calls.leave_call(chat_id)
            except Exception as exc:
                log.warning("Leave call issue for %s: %s", chat_id, exc)

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
        self.calls = None
        self.client = None
        self._handler_registered = False

    def _transcribe(self, pcm: bytes) -> str:
        import speech_recognition as sr
        import audioop

        try:
            # stereo 48k → mono 16k
            mono = audioop.tomono(pcm, 2, 0.5, 0.5)
            mono_16k = audioop.ratecv(mono, 2, 1, 48000, 16000, None)[0]

            recognizer = sr.Recognizer()
            audio = sr.AudioData(mono_16k, 16000, 2)
            return recognizer.recognize_google(audio, language=STT_LANGUAGE)
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as exc:
            log.warning("Speech recognition unavailable: %s", exc)
            return ""
        except Exception as exc:
            log.warning("Transcribe error: %s", exc)
            return ""

    @staticmethod
    def _remove_wake_word(text: str) -> str:
        return re.sub(re.escape(WAKE_WORD), "", text, flags=re.IGNORECASE).strip(" ,:;.-")

    async def _answer_in_voice(self, chat_id: int, prompt: str):
        try:
            answer = await asyncio.to_thread(ask_ai, prompt)
            if not answer:
                answer = "Sorry, I didn't get that."
            await self._speak(chat_id, answer)
        except Exception:
            log.exception("Failed to answer in voice for %s", chat_id)

    async def _speak(self, chat_id: int, text: str):
        import edge_tts
        import subprocess
        import imageio_ffmpeg
        from pytgcalls.types import Device, ExternalMedia, MediaStream
        from pytgcalls.types.raw import AudioParameters

        self.speaking.add(chat_id)
        try:
            with tempfile.TemporaryDirectory(prefix="missti_tts_") as tmp:
                mp3 = os.path.join(tmp, "reply.mp3")
                raw = os.path.join(tmp, "reply.raw")

                communicate = edge_tts.Communicate(text[:1200], TTS_VOICE)
                await communicate.save(mp3)

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

                # Make sure external stream is active
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
                with open(raw, "rb") as stream:
                    while True:
                        frame = stream.read(frame_size)
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
