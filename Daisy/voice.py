"""
voice.py
Voice command listener, Push-To-Talk (CapsLock) support, and speech synthesis for Daisy.

Supports commands like:
- "run", "sprint", "fast" -> runs at high speed
- "walk", "go", "move", "stroll" -> walks
- "jump", "hop", "bounce", "leap" -> jumps
- "sit", "rest", "stop", "freeze", "idle" -> sits/rests
- "exit", "quit", "close", "bye", "goodbye" -> exits Daisy
- "ask [question]" or any general query -> routes to Gemini Q&A
"""

import os
import sys
import time
import threading
from typing import Dict, Any, Optional
import numpy as np
import sounddevice as sd
import speech_recognition as sr
import pyttsx3
from PyQt5.QtCore import QThread, pyqtSignal

# Windows Virtual Key code for CapsLock
VK_CAPITAL = 0x14


def is_capslock_pressed() -> bool:
    """Checks if CapsLock is physically pressed down globally across Windows."""
    if sys.platform == "win32":
        try:
            import ctypes
            return (ctypes.windll.user32.GetAsyncKeyState(VK_CAPITAL) & 0x8000) != 0
        except Exception:
            return False
    return False


def record_audio_clip(duration: float = 3.5, samplerate: int = 16000) -> sr.AudioData:
    """Records audio from default microphone and returns a SpeechRecognition AudioData object."""
    num_samples = int(duration * samplerate)
    raw_audio = sd.rec(num_samples, samplerate=samplerate, channels=1, dtype="int16")
    sd.wait()
    return sr.AudioData(raw_audio.tobytes(), samplerate, 2)


def transcribe_audio(audio_data: sr.AudioData) -> str:
    """Transcribes an AudioData clip using Google's free Web Speech recognition."""
    recognizer = sr.Recognizer()
    try:
        text = recognizer.recognize_google(audio_data)
        return text.strip()
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as exc:
        raise RuntimeError(f"Speech recognition service error: {exc}") from exc


def parse_voice_command(text: str) -> Dict[str, Any]:
    """Parses a transcribed string into an actionable Daisy command dictionary."""
    if not text:
        return {"action": "none", "raw": ""}

    t = text.lower().strip()

    # 1. Exit / Quit (High priority)
    if any(k in t for k in ["exit", "quit", "close", "bye", "goodbye", "close daisy", "exit daisy", "stop program"]):
        return {"action": "exit", "raw": text}

    # 2. Pet Switching (High priority)
    if any(k in t for k in ["pink monster", "pink pet", "pink character"]):
        return {"action": "switch_pet", "pet": "pink_monster", "raw": text}
    if any(k in t for k in ["owlet monster", "owlet", "owl monster", "owl pet"]):
        return {"action": "switch_pet", "pet": "owlet_monster", "raw": text}
    if any(k in t for k in ["dude monster", "dude pet", "dude character"]):
        return {"action": "switch_pet", "pet": "dude_monster", "raw": text}
    if any(k in t for k in ["switch to cat", "select cat", "choose cat", "cat pet", "daisy cat"]):
        return {"action": "switch_pet", "pet": "cat", "raw": text}

    # 3. Action commands (Attack, Throw, Hurt)
    if any(k in t for k in ["attack", "punch", "strike", "fight", "slash"]):
        return {"action": "attack", "raw": text}
    if any(k in t for k in ["throw", "throw rock", "rock", "toss"]):
        return {"action": "throw", "raw": text}
    if any(k in t for k in ["hurt", "ouch", "pain"]):
        return {"action": "hurt", "raw": text}

    # 4. Run (higher priority than walk)
    if any(k in t for k in ["run", "sprint", "run faster", "running", "fast"]):
        return {"action": "run", "speed": 4, "raw": text}

    # 5. Walk
    if any(k in t for k in ["walk", "walking", "move", "go ahead", "stroll", "go"]):
        return {"action": "walk", "speed": 2, "raw": text}

    # 6. Jump
    if any(k in t for k in ["jump", "jumping", "hop", "hopping", "leap", "bounce"]):
        return {"action": "jump", "raw": text}

    # 7. Sit / Rest / Stop / Idle
    if any(k in t for k in ["sit", "sit down", "rest", "stop", "freeze", "idle", "relax", "stay"]):
        return {"action": "sit", "raw": text}

    # 8. Question to Daisy
    for prefix in [
        "ask daisy", "ask", "daisy", "tell me", "can you tell me",
        "what is", "why is", "who is", "how do", "how is", "where is", "when did"
    ]:
        if t.startswith(prefix):
            q = text[len(prefix):].strip(" ,:?")
            if not q:
                q = text
            return {"action": "ask", "question": q, "raw": text}

    # Default to asking question if it looks like a phrase or question
    return {"action": "ask", "question": text, "raw": text}


class VoiceWorker(QThread):
    """Background worker thread that listens to microphone and parses voice commands."""

    started_listening = pyqtSignal()
    finished_command = pyqtSignal(dict, str)  # (parsed_dict, raw_transcript)
    finished_error = pyqtSignal(str)

    def __init__(self, duration: float = 3.5):
        super().__init__()
        self.duration = duration
        self._is_running = True

    def run(self):
        try:
            self.started_listening.emit()
            audio_data = record_audio_clip(duration=self.duration)
            if not self._is_running:
                return

            transcript = transcribe_audio(audio_data)

            if not transcript:
                self.finished_error.emit("No speech detected. Try speaking clearly into the microphone.")
                return

            cmd = parse_voice_command(transcript)
            self.finished_command.emit(cmd, transcript)

        except Exception as exc:
            self.finished_error.emit(str(exc))

    def stop(self):
        self._is_running = False


class PushToTalkListener(QThread):
    """Global Push-To-Talk listener using CapsLock.
    
    - Hold CapsLock to record audio.
    - Release CapsLock to stop recording, transcribe, and execute command.
    """

    started_recording = pyqtSignal()
    finished_command = pyqtSignal(dict, str)  # (cmd_dict, transcript)
    finished_error = pyqtSignal(str)

    def __init__(self, sample_rate: int = 16000):
        super().__init__()
        self.sample_rate = sample_rate
        self._active = True
        self._is_recording = False
        self._frames = []
        self._stream = None

    def run(self):
        was_pressed = False

        def _audio_callback(indata, frame_count, time_info, status):
            if self._is_recording:
                self._frames.append(indata.copy())

        while self._active:
            pressed = is_capslock_pressed()

            # Key pressed down (Start Recording)
            if pressed and not was_pressed:
                was_pressed = True
                self._frames = []
                self._is_recording = True
                try:
                    self._stream = sd.InputStream(
                        samplerate=self.sample_rate,
                        channels=1,
                        dtype="int16",
                        callback=_audio_callback,
                    )
                    self._stream.start()
                    self.started_recording.emit()
                except Exception as exc:
                    self.finished_error.emit(f"Microphone error: {exc}")
                    self._is_recording = False

            # Key released (Stop Recording & Transcribe)
            elif not pressed and was_pressed:
                was_pressed = False
                self._is_recording = False
                if self._stream:
                    try:
                        self._stream.stop()
                        self._stream.close()
                    except Exception:
                        pass
                    self._stream = None

                if self._frames:
                    try:
                        audio_np = np.concatenate(self._frames, axis=0)
                        # Ensure recording is longer than 0.25 seconds
                        if len(audio_np) >= int(self.sample_rate * 0.25):
                            audio_data = sr.AudioData(audio_np.tobytes(), self.sample_rate, 2)
                            transcript = transcribe_audio(audio_data)
                            if transcript:
                                cmd = parse_voice_command(transcript)
                                self.finished_command.emit(cmd, transcript)
                            else:
                                self.finished_error.emit("No speech detected.")
                    except Exception as exc:
                        self.finished_error.emit(str(exc))

            time.sleep(0.02)  # Low CPU polling

    def stop(self):
        self._active = False
        self._is_recording = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
        self.wait(500)


class ContinuousVoiceListener(QThread):
    """Continuous background listener that constantly listens for Daisy voice commands."""

    command_detected = pyqtSignal(dict, str)
    status_changed = pyqtSignal(str)

    def __init__(self, clip_duration: float = 3.0):
        super().__init__()
        self.clip_duration = clip_duration
        self._active = True

    def run(self):
        self.status_changed.emit("listening")
        while self._active:
            try:
                audio_data = record_audio_clip(duration=self.clip_duration)
                if not self._active:
                    break

                transcript = transcribe_audio(audio_data)
                if transcript and self._active:
                    cmd = parse_voice_command(transcript)
                    if cmd.get("action") != "none":
                        self.command_detected.emit(cmd, transcript)
            except Exception:
                pass
        self.status_changed.emit("stopped")

    def stop(self):
        self._active = False


# Background TTS engine instance
_tts_lock = threading.Lock()

# Curated cute voices tailored for Daisy's adorable pet personality
CUTE_VOICES: Dict[str, Dict[str, str]] = {
    "ana": {
        "name": "Ana (Super Cute & Playful 🌸)",
        "voice": "en-US-AnaNeural",
        "pitch": "+6Hz",
        "rate": "+4%",
        "description": "Sweet, high-spirited cartoon pet voice",
    },
    "jenny": {
        "name": "Jenny (Warm & Cheerful 🎀)",
        "voice": "en-US-JennyNeural",
        "pitch": "+4Hz",
        "rate": "+3%",
        "description": "Bubbly, friendly and warm young female",
    },
    "emma": {
        "name": "Emma (Sweet & Bubbly ✨)",
        "voice": "en-US-EmmaNeural",
        "pitch": "+5Hz",
        "rate": "+4%",
        "description": "Gentle, perky and sweet voice",
    },
    "maisie": {
        "name": "Maisie (Cute British 🌷)",
        "voice": "en-GB-MaisieNeural",
        "pitch": "+4Hz",
        "rate": "+3%",
        "description": "Cute and cheerful British accent",
    },
    "ava": {
        "name": "Ava (Soft & Gentle 💖)",
        "voice": "en-US-AvaNeural",
        "pitch": "+3Hz",
        "rate": "+2%",
        "description": "Expressive, soft and affectionate voice",
    },
}

DEFAULT_VOICE_KEY = "ana"


def get_voice_config_path() -> str:
    """Returns the path to the local voice configuration file."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        try:
            test_file = os.path.join(exe_dir, ".test_write")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            base_dir = exe_dir
        except Exception:
            appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
            base_dir = os.path.join(appdata, "Daisy")
            os.makedirs(base_dir, exist_ok=True)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, ".voice_config")


def get_current_voice() -> str:
    """Loads the currently selected voice key, defaulting to 'ana'."""
    config_file = get_voice_config_path()
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                saved_key = f.read().strip().lower()
                if saved_key in CUTE_VOICES:
                    return saved_key
        except Exception:
            pass
    return DEFAULT_VOICE_KEY


def set_current_voice(voice_key: str) -> str:
    """Saves the selected voice key and returns it."""
    clean_key = voice_key.strip().lower()
    if clean_key not in CUTE_VOICES:
        clean_key = DEFAULT_VOICE_KEY

    config_file = get_voice_config_path()
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(clean_key)
    except Exception:
        pass
    return clean_key


def get_cute_voices() -> Dict[str, Dict[str, str]]:
    """Returns dictionary of available cute voices."""
    return CUTE_VOICES


def _speak_pyttsx3_fallback(text: str) -> None:
    """Fallback offline TTS using pyttsx3 with female voice."""
    try:
        engine = pyttsx3.init()
        # Find female voice (e.g. Zira)
        voices = engine.getProperty("voices")
        female_voice = None
        for v in voices:
            v_name = v.name.lower()
            v_gender = str(getattr(v, "gender", "")).lower()
            if "zira" in v_name or "female" in v_gender or "eva" in v_name or "hazel" in v_name:
                female_voice = v.id
                break
        if female_voice:
            engine.setProperty("voice", female_voice)
        elif voices and len(voices) > 1:
            engine.setProperty("voice", voices[1].id)

        engine.setProperty("rate", 175)  # Cheerful pace
        engine.say(text)
        engine.runAndWait()
    except Exception:
        pass


def _speak_edge_tts(text: str, voice_key: str) -> bool:
    """Synthesizes and plays audio using edge-tts and sounddevice."""
    import asyncio
    import io
    import soundfile as sf
    import edge_tts

    voice_profile = CUTE_VOICES.get(voice_key, CUTE_VOICES[DEFAULT_VOICE_KEY])
    voice_id = voice_profile["voice"]
    pitch = voice_profile.get("pitch", "+6Hz")
    rate = voice_profile.get("rate", "+4%")

    async def _generate():
        comm = edge_tts.Communicate(text, voice_id, pitch=pitch, rate=rate)
        bio = io.BytesIO()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                bio.write(chunk["data"])
        bio.seek(0)
        return sf.read(bio)

    try:
        data, fs = asyncio.run(_generate())
        if len(data) > 0:
            sd.play(data, fs)
            sd.wait()
            return True
    except Exception:
        return False
    return False


def speak_async(text: str, voice_key: Optional[str] = None) -> None:
    """Speaks text asynchronously using Daisy's cute girl voice with fallback."""
    if not text:
        return

    # Strip any emojis or speech bubble symbols that shouldn't be read out loud
    clean_text = text
    for symbol in ["🎤", "🔊", "🔈", "🐾", "🏃", "🐱", "💤", "👋", "🌸", "🎀", "✨", "🌷", "💖"]:
        clean_text = clean_text.replace(symbol, "")
    clean_text = clean_text.strip()
    if not clean_text:
        return

    selected_voice = voice_key or get_current_voice()

    def _worker():
        with _tts_lock:
            # 1. Try cute neural voice via edge-tts
            success = _speak_edge_tts(clean_text, selected_voice)
            # 2. Fallback to pyttsx3 female voice if offline or failed
            if not success:
                _speak_pyttsx3_fallback(clean_text)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

