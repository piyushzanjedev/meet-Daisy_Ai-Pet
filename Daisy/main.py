"""
main.py
Entry point for Daisy. Wires together the pet widget (body), the system
tray menu (commands & multi-pet selection), the Gemini/OpenAI/Groq brain (Q&A),
custom font (Planes_ValMore), and the voice recognition engine with global
Push-To-Talk via CapsLock.

Run with:  python main.py
"""

import sys
from datetime import datetime
from PyQt5 import QtCore, QtGui, QtWidgets
from pet_widget import PetWidget, PET_INFO, get_pet_font_family
import brain
import voice


def get_time_of_day_greeting(now: datetime = None) -> tuple:
    """Returns (bubble_text, speech_text) — bubble_text includes a cute emoji
    for the speech bubble; speech_text is emoji-free for clean TTS playback."""
    hour = (now or datetime.now()).hour

    if 5 <= hour < 12:
        return ("Good morning! ☀️ I'm awake and ready to play!", "Good morning! I'm awake and ready to play!")
    elif 12 <= hour < 17:
        return ("Good afternoon! 🌼 Hope your day is going well!", "Good afternoon! Hope your day is going well!")
    elif 17 <= hour < 21:
        return ("Good evening! 🌇 Let's wind down together!", "Good evening! Let's wind down together!")
    else:
        return ("It's late... 🌙 shouldn't you be sleeping? Hehe, hi!", "It's late, shouldn't you be sleeping? Hehe, hi!")


class AskWorker(QtCore.QThread):
    """Runs the (possibly slow) Gemini call off the UI thread."""

    finished_ok = QtCore.pyqtSignal(str)
    finished_err = QtCore.pyqtSignal(str)

    def __init__(self, question: str):
        super().__init__()
        self.question = question

    def run(self):
        try:
            answer = brain.ask(self.question)
            self.finished_ok.emit(answer)
        except brain.BrainError as exc:
            self.finished_err.emit(str(exc))
        except Exception as exc:  # pragma: no cover - safety net
            self.finished_err.emit(f"Unexpected error: {exc}")


class DaisyApp(QtCore.QObject):
    def __init__(self):
        super().__init__()
        self.app = QtWidgets.QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # Apply custom font and sleek dark styling
        font_family = get_pet_font_family()
        self.app.setFont(QtGui.QFont(font_family, 10))
        self.app.setStyleSheet(f"""
            QMenu {{
                background-color: #242424;
                color: #f0f0f0;
                border: 1px solid #3d3d3d;
                border-radius: 8px;
                padding: 6px;
                font-family: "{font_family}", "Segoe UI", sans-serif;
            }}
            QMenu::item {{
                padding: 6px 22px 6px 18px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: #5c6bc0;
                color: #ffffff;
            }}
            QMenu::item:checked {{
                font-weight: bold;
                color: #81c784;
            }}
            QMenu::separator {{
                height: 1px;
                background: #3d3d3d;
                margin: 4px 6px;
            }}
        """)

        self._worker = None  # keep a reference so AskWorker isn't garbage-collected
        self._voice_worker = None  # VoiceWorker reference
        self._continuous_listener = None  # ContinuousVoiceListener reference
        self._ptt_listener = None  # PushToTalkListener reference (CapsLock)
        self.continuous_listening = False

        self.app.aboutToQuit.connect(self._cleanup)

        self.pet = PetWidget()
        self.app.setWindowIcon(self._make_icon())
        self.pet.on_right_click = self.show_menu
        self.pet.on_double_click = self.ask_question
        self.pet.on_middle_click = self.listen_voice_command
        self.pet.on_pet_changed = self._on_pet_changed
        self.pet.show()

        # Greet with a cute, time-aware message as soon as pet appears
        bubble_text, speech_text = get_time_of_day_greeting()
        self.pet.say(bubble_text, seconds=8)
        voice.speak_async(speech_text)

        self.tray = QtWidgets.QSystemTrayIcon(self._make_icon())
        self.tray.setToolTip(f"Daisy ({self.pet.get_current_pet_name()}) — Hold CapsLock to Talk")
        self.tray.setContextMenu(self._build_menu())
        self.tray.activated.connect(self._tray_clicked)
        self.tray.show()

        # Start Global Push-To-Talk listener (CapsLock)
        self._start_push_to_talk()

    # ---------------- tray / menu ----------------

    def _make_icon(self) -> QtGui.QIcon:
        if hasattr(self, "pet") and hasattr(self.pet, "sprites") and self.pet.sprites.get("idle"):
            frame = self.pet.sprites["idle"][0]
            scaled = frame.scaled(32, 32, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            return QtGui.QIcon(scaled)
        pix = QtGui.QPixmap(32, 32)
        pix.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pix)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setBrush(QtGui.QColor(146, 208, 132))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()
        return QtGui.QIcon(pix)

    def _build_menu(self) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu()

        # Voice controls
        menu.addAction("🎤 Push-To-Talk: Hold CapsLock (or click here)", self.listen_voice_command)
        continuous_label = "🔊 Continuous Voice Mode: [ON]" if self.continuous_listening else "🔈 Continuous Voice Mode: [OFF]"
        menu.addAction(continuous_label, self.toggle_continuous_listening)
        menu.addSeparator()

        # Pet Selection Submenu
        pet_menu = menu.addMenu("🐾 Select Pet")
        for pet_id, info in PET_INFO.items():
            action = pet_menu.addAction(f"{info['icon']} {info['name']}")
            action.setCheckable(True)
            action.setChecked(self.pet.current_pet == pet_id)
            # Connect with bound pet_id
            action.triggered.connect(lambda checked, pid=pet_id: self.change_pet(pid))

        menu.addSeparator()

        # Motion & Actions
        menu.addAction("Walk", lambda: self.pet.set_state("walk", speed=2))
        menu.addAction("Run", lambda: self.pet.set_state("walk", speed=4))
        menu.addAction("Jump", lambda: self.pet.set_state("jump"))
        menu.addAction("Sit", lambda: self.pet.set_state("sit"))

        # Extra Monster Actions when available
        if "attack" in self.pet.sprites:
            menu.addAction("⚔️ Attack / Strike", lambda: self.pet.set_state("attack"))
        if "throw" in self.pet.sprites:
            menu.addAction("🪨 Throw Rock", lambda: self.pet.set_state("throw"))

        menu.addSeparator()

        # AI Q&A and Settings
        menu.addAction("Ask Daisy a question...", self.ask_question)
        menu.addAction("Set API Key (Gemini / OpenAI / Groq)...", self.set_api_key)
        menu.addSeparator()

        # Exit
        menu.addAction("Quit", self.app.quit)
        return menu

    def change_pet(self, pet_id: str):
        """Switches the active pet and refreshes UI icons and menus."""
        self.pet.set_pet(pet_id)
        info = PET_INFO.get(pet_id, {})
        pet_name = info.get("name", "Pet")
        icon = info.get("icon", "")
        self.pet.say(f"Switched to {pet_name}! {icon}", seconds=6)
        voice.speak_async(f"Switched to {pet_name}")
        self._refresh_pet_ui()

    def _on_pet_changed(self, pet_id: str):
        """Callback from PetWidget when pet changes."""
        self._refresh_pet_ui()

    def _refresh_pet_ui(self):
        """Updates icons, tooltips, and context menus for the current pet."""
        icon = self._make_icon()
        self.app.setWindowIcon(icon)
        if hasattr(self, "tray") and self.tray:
            self.tray.setIcon(icon)
            self.tray.setToolTip(f"Daisy ({self.pet.get_current_pet_name()}) — Hold CapsLock to Talk")
            self.tray.setContextMenu(self._build_menu())

    def _tray_clicked(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.DoubleClick:
            self.ask_question()

    def show_menu(self, global_pos):
        self._build_menu().exec_(global_pos)

    # ---------------- Voice Commands & Push-To-Talk ----------------

    def _start_push_to_talk(self):
        """Initializes and runs the global CapsLock Push-To-Talk listener."""
        try:
            self._ptt_listener = voice.PushToTalkListener()
            self._ptt_listener.started_recording.connect(self._on_ptt_started)
            self._ptt_listener.finished_command.connect(self.execute_voice_command)
            self._ptt_listener.finished_error.connect(self._on_voice_error)
            self._ptt_listener.start()
        except Exception:
            pass

    def _on_ptt_started(self):
        self.pet.say("🎤 Listening... (Release CapsLock when done)", seconds=10)

    def listen_voice_command(self):
        """Starts a single-shot voice recognition listening session."""
        if self._voice_worker and self._voice_worker.isRunning():
            return

        self.pet.say("🎤 Listening... (Say: run, walk, jump, sit, switch pet, exit)", seconds=5)
        self._voice_worker = voice.VoiceWorker(duration=3.5)
        self._voice_worker.started_listening.connect(lambda: self.pet.say("🎤 Listening now...", seconds=4))
        self._voice_worker.finished_command.connect(self.execute_voice_command)
        self._voice_worker.finished_error.connect(self._on_voice_error)
        self._voice_worker.start()

    def toggle_continuous_listening(self):
        """Toggles background continuous listening mode."""
        self.continuous_listening = not self.continuous_listening
        if self.continuous_listening:
            self.pet.say("🔊 Continuous voice listening ON!", seconds=4)
            self._continuous_listener = voice.ContinuousVoiceListener(clip_duration=3.0)
            self._continuous_listener.command_detected.connect(self.execute_voice_command)
            self._continuous_listener.start()
        else:
            self.pet.say("🔈 Continuous voice listening OFF", seconds=4)
            if self._continuous_listener:
                self._continuous_listener.stop()
                self._continuous_listener = None
        self.tray.setContextMenu(self._build_menu())

    def execute_voice_command(self, cmd: dict, transcript: str):
        """Dispatches an identified voice command."""
        action = cmd.get("action")

        if action == "switch_pet":
            pet_id = cmd.get("pet", "cat")
            self.change_pet(pet_id)

        elif action == "attack":
            self.pet.set_state("attack")
            self.pet.say(f"Attack! ⚔️ (Heard: '{transcript}')", seconds=6)
            voice.speak_async("Attack!")

        elif action == "throw":
            self.pet.set_state("throw")
            self.pet.say(f"Throwing rock! 🪨 (Heard: '{transcript}')", seconds=6)
            voice.speak_async("Throwing rock!")

        elif action == "hurt":
            self.pet.set_state("hurt")
            self.pet.say(f"Ouch! 💥 (Heard: '{transcript}')", seconds=6)
            voice.speak_async("Ouch!")

        elif action == "run":
            self.pet.set_state("walk", speed=4)
            self.pet.say(f"Running fast! 🏃 (Heard: '{transcript}')", seconds=6)
            voice.speak_async("Running fast!")

        elif action == "walk":
            self.pet.set_state("walk", speed=2)
            self.pet.say(f"Walking! 🐾 (Heard: '{transcript}')", seconds=6)
            voice.speak_async("Walking!")

        elif action == "jump":
            self.pet.set_state("jump")
            self.pet.say(f"Wheee! 🐱 (Heard: '{transcript}')", seconds=6)
            voice.speak_async("Wheee!")

        elif action == "sit":
            self.pet.set_state("sit")
            self.pet.say(f"Resting! 💤 (Heard: '{transcript}')", seconds=6)
            voice.speak_async("Resting!")

        elif action == "exit":
            self.pet.say(f"Goodbye! 👋 (Heard: '{transcript}')", seconds=3)
            voice.speak_async("Goodbye!")
            QtCore.QTimer.singleShot(1200, self.app.quit)

        elif action == "ask":
            question = cmd.get("question", transcript)
            self.pet.say(f"Thinking: '{question}'...", seconds=30)
            self._ask_gemini(question)

    def _on_voice_error(self, message: str):
        self.pet.say(f"Oops: {message}", seconds=6)

    # ---------------- Q&A flow ----------------

    def ask_question(self):
        question, ok = QtWidgets.QInputDialog.getText(
            None, "Ask Daisy", "What do you want to ask?"
        )
        if not ok or not question.strip():
            return

        self.pet.say("Thinking...", seconds=30)
        self._ask_gemini(question.strip())

    def _ask_gemini(self, question: str):
        if self._worker and self._worker.isRunning():
            self.pet.say("Still thinking about your previous question...", seconds=4)
            return

        self._worker = AskWorker(question)
        self._worker.finished_ok.connect(self._on_answer)
        self._worker.finished_err.connect(self._on_error)
        self._worker.start()

    def _on_answer(self, answer: str):
        self.pet.say(answer, seconds=10)
        voice.speak_async(answer)

    def set_api_key(self):
        masked, provider_name = brain.get_key_status()
        prompt = (
            "Enter your Google Gemini, OpenAI, or Groq API Key:\n\n"
            "• Google Gemini (Free): https://aistudio.google.com/apikey\n"
            "• Groq (Free, no card): https://console.groq.com/keys\n"
            "• OpenAI (sk-...): https://platform.openai.com/api-keys\n\n"
            "Daisy will automatically detect whether it is Gemini, OpenAI, or Groq."
        )
        if masked:
            prompt += f"\n\nCurrent key: {masked} ({provider_name})"
        key, ok = QtWidgets.QInputDialog.getText(
            None, "Set API Key", prompt, QtWidgets.QLineEdit.Normal
        )
        if ok and key.strip():
            raw_key = key.strip()
            detected = brain.detect_provider(raw_key).capitalize()
            try:
                saved_path = brain.save_api_key(raw_key)
                self.pet.say(f"API Key saved! Provider: {detected}", seconds=6)
                print(f"[Daisy] API key persisted to: {saved_path}")
            except brain.BrainError as exc:
                self.pet.say(f"Oops: {exc}", seconds=15)

    def _on_error(self, message: str):
        self.pet.say(f"Oops: {message}", seconds=12)

    def _cleanup(self):
        """Stops background threads cleanly on application exit."""
        if self._ptt_listener:
            self._ptt_listener.stop()
            self._ptt_listener = None
        if self._continuous_listener:
            self._continuous_listener.stop()
            self._continuous_listener = None
        if self._voice_worker and self._voice_worker.isRunning():
            self._voice_worker.stop()

    # ---------------- run ----------------

    def run(self):
        sys.exit(self.app.exec_())


if __name__ == "__main__":
    DaisyApp().run()
