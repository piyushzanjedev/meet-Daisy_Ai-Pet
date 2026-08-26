"""
main.py
Entry point for Daisy. Wires together the pet widget (body), the system
tray menu (commands & multi-pet selection), the Gemini/OpenAI/Groq brain (Q&A),
custom font (Planes_ValMore), and the voice recognition engine with global
Push-To-Talk via CapsLock.

Run with:  python main.py
"""

from typing import Optional
import sys
from datetime import datetime
from PyQt5 import QtCore, QtGui, QtWidgets
from pet_widget import PetWidget, PET_INFO, get_pet_font_family
import brain
import voice
import jarvis_engine


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

    def __init__(self, question: str, pet_name: str = "Daisy"):
        super().__init__()
        self.question = question
        self.pet_name = pet_name

    def run(self):
        try:
            answer = brain.ask(self.question, pet_name=self.pet_name)
            self.finished_ok.emit(answer)
        except brain.BrainError as exc:
            self.finished_err.emit(str(exc))
        except Exception as exc:  # pragma: no cover - safety net
            self.finished_err.emit(f"Unexpected error: {exc}")


class JarvisWorker(QtCore.QThread):
    """Executes Jarvis desktop automation commands off the Qt UI thread."""

    finished_ok = QtCore.pyqtSignal(str, dict)
    finished_err = QtCore.pyqtSignal(str)

    def __init__(self, command: str):
        super().__init__()
        self.command = command

    def run(self):
        try:
            res = jarvis_engine.execute_jarvis_command(self.command)
            self.finished_ok.emit(res.get("message", "Done!"), res)
        except Exception as exc:
            self.finished_err.emit(str(exc))


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
        self._jarvis_worker = None  # JarvisWorker reference
        self._voice_worker = None  # VoiceWorker reference
        self._continuous_listener = None  # ContinuousVoiceListener reference
        self._ptt_listener = None  # PushToTalkListener reference (CapsLock)
        self.continuous_listening = False

        # Start background indexing of apps, shortcuts, and Steam games
        jarvis_engine.start_background_indexing()

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
        voice.speak_async(speech_text, pet_id=self.pet.current_pet)

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

        # Jarvis Desktop Assistant Tools
        jarvis_menu = menu.addMenu("⚡ Jarvis Assistant / PC Tools")
        jarvis_menu.addAction("📸 Take Screenshot", lambda: self._execute_jarvis("take a screenshot"))
        jarvis_menu.addAction("🗑️ Empty Recycle Bin", lambda: self._execute_jarvis("empty recycle bin"))
        jarvis_menu.addAction("🔒 Lock Screen", lambda: self._execute_jarvis("lock screen"))
        jarvis_menu.addAction("⏰ What Time Is It", lambda: self._execute_jarvis("what time is it"))
        jarvis_menu.addAction("📅 Today's Date", lambda: self._execute_jarvis("what's today's date"))
        jarvis_menu.addSeparator()
        jarvis_menu.addAction("🔄 Re-index Installed Apps & Games", self._reindex_apps)
        jarvis_menu.addAction("⚙️ Assistant Settings (GitHub / Autostart)...", self._open_jarvis_settings)

        menu.addSeparator()

        # AI Q&A and Settings
        menu.addAction("Ask or Command Daisy...", self.ask_question)
        menu.addAction("Set API Key (Gemini / OpenAI / Groq)...", self.set_api_key)
        menu.addSeparator()

        # Exit
        menu.addAction("Quit", self.app.quit)
        return menu

    def speak(self, text: str, pet_id: Optional[str] = None):
        """Speaks text using the currently selected or specified pet's cute voice."""
        target_pet = pet_id or self.pet.current_pet
        voice.speak_async(text, pet_id=target_pet)

    def change_pet(self, pet_id: str):
        """Switches the active pet and refreshes UI icons and menus."""
        self.pet.set_pet(pet_id)
        info = PET_INFO.get(pet_id, {})
        pet_name = info.get("name", "Pet")
        icon = info.get("icon", "")
        self.pet.say(f"Switched to {pet_name}! {icon}", seconds=6)
        self.speak(f"Switched to {pet_name}", pet_id=pet_id)
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

        self.pet.say("🎤 Listening... (Say: run, jump, open chrome, search python, switch pet, exit)", seconds=5)
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
            self.speak("Attack!")

        elif action == "throw":
            self.pet.set_state("throw")
            self.pet.say(f"Throwing rock! 🪨 (Heard: '{transcript}')", seconds=6)
            self.speak("Throwing rock!")

        elif action == "hurt":
            self.pet.set_state("hurt")
            self.pet.say(f"Ouch! 💥 (Heard: '{transcript}')", seconds=6)
            self.speak("Ouch!")

        elif action == "run":
            self.pet.set_state("walk", speed=4)
            self.pet.say(f"Running fast! 🏃 (Heard: '{transcript}')", seconds=6)
            self.speak("Running fast!")

        elif action == "walk":
            self.pet.set_state("walk", speed=2)
            self.pet.say(f"Walking! 🐾 (Heard: '{transcript}')", seconds=6)
            self.speak("Walking!")

        elif action == "jump":
            self.pet.set_state("jump")
            self.pet.say(f"Wheee! 🐱 (Heard: '{transcript}')", seconds=6)
            self.speak("Wheee!")

        elif action == "sit":
            self.pet.set_state("sit")
            self.pet.say(f"Resting! 💤 (Heard: '{transcript}')", seconds=6)
            self.speak("Resting!")

        elif action == "exit":
            self.pet.say(f"Goodbye! 👋 (Heard: '{transcript}')", seconds=3)
            self.speak("Goodbye!")
            QtCore.QTimer.singleShot(1200, self.app.quit)

        elif action == "jarvis":
            command = cmd.get("command", transcript)
            self.pet.say(f"Working on it... ⚡", seconds=5)
            self._execute_jarvis(command)

        elif action == "ask":
            question = cmd.get("question", transcript)
            self.pet.say(f"Thinking: '{question}'...", seconds=30)
            self._ask_gemini(question)

    def _on_voice_error(self, message: str):
        self.pet.say(f"Oops: {message}", seconds=6)

    # ---------------- Jarvis Execution flow ----------------

    def _execute_jarvis(self, command: str):
        """Executes a Jarvis automation command asynchronously."""
        if self._jarvis_worker and self._jarvis_worker.isRunning():
            self.pet.say("Working on the previous command...", seconds=4)
            return

        self._jarvis_worker = JarvisWorker(command)
        self._jarvis_worker.finished_ok.connect(self._on_jarvis_ok)
        self._jarvis_worker.finished_err.connect(self._on_jarvis_err)
        self._jarvis_worker.start()

    def _on_jarvis_ok(self, message: str, details: dict):
        self.pet.say(message, seconds=8)
        self.speak(message)

    def _on_jarvis_err(self, err_msg: str):
        self.pet.say(f"Oops: {err_msg}", seconds=8)
        self.speak(f"Sorry, {err_msg}")

    def _reindex_apps(self):
        self.pet.say("Re-indexing installed apps and games...", seconds=5)
        self.speak("Re-indexing installed applications.")
        jarvis_engine.start_background_indexing()

    def _open_jarvis_settings(self):
        cfg = jarvis_engine.load_config()
        current_gh = cfg.get("github_username", "")
        autostart_on = jarvis_engine.is_autostart_enabled()

        dialog = QtWidgets.QDialog()
        dialog.setWindowTitle("Jarvis Assistant Settings")
        dialog.setMinimumWidth(380)
        layout = QtWidgets.QVBoxLayout(dialog)

        gh_label = QtWidgets.QLabel("GitHub Username (for 'open my github repo'):")
        gh_input = QtWidgets.QLineEdit(current_gh)
        layout.addWidget(gh_label)
        layout.addWidget(gh_input)

        autostart_cb = QtWidgets.QCheckBox("Start Daisy automatically with Windows")
        autostart_cb.setChecked(autostart_on)
        layout.addWidget(autostart_cb)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        layout.addWidget(btns)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            new_gh = gh_input.text().strip()
            cfg["github_username"] = new_gh
            jarvis_engine.save_config(cfg)

            new_autostart = autostart_cb.isChecked()
            if new_autostart != autostart_on:
                try:
                    if new_autostart:
                        jarvis_engine.enable_autostart()
                    else:
                        jarvis_engine.disable_autostart()
                except Exception as exc:
                    self.pet.say(f"Autostart error: {exc}", seconds=6)

            self.pet.say("Settings updated! ✨", seconds=5)
            self.speak("Settings updated.")

    # ---------------- Q&A flow ----------------

    def ask_question(self):
        prompt = (
            "Ask a question or give a PC command:\n\n"
            "• AI Questions: 'Why is the sky blue?', 'Tell me a joke'\n"
            "• PC Commands: 'open chrome', 'search python', 'take a screenshot', 'close spotify', 'what time is it'"
        )
        text, ok = QtWidgets.QInputDialog.getText(
            None, f"Ask / Command {self.pet.get_current_pet_name()}", prompt
        )
        if not ok or not text.strip():
            return

        cleaned = text.strip()
        if jarvis_engine.is_jarvis_command(cleaned):
            self.pet.say("Working on it... ⚡", seconds=5)
            self._execute_jarvis(cleaned)
        else:
            self.pet.say("Thinking...", seconds=30)
            self._ask_gemini(cleaned)

    def _ask_gemini(self, question: str):
        if self._worker and self._worker.isRunning():
            self.pet.say("Still thinking about your previous question...", seconds=4)
            return

        self._worker = AskWorker(question, pet_name=self.pet.get_current_pet_name())
        self._worker.finished_ok.connect(self._on_answer)
        self._worker.finished_err.connect(self._on_error)
        self._worker.start()

    def _on_answer(self, answer: str):
        self.pet.say(answer, seconds=10)
        self.speak(answer)

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
        if self._jarvis_worker and self._jarvis_worker.isRunning():
            self._jarvis_worker.terminate()

    # ---------------- run ----------------

    def run(self):
        sys.exit(self.app.exec_())


if __name__ == "__main__":
    DaisyApp().run()
