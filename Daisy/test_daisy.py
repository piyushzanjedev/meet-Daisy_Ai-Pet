import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure headless Qt for testing environment
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5 import QtWidgets, QtCore, QtGui
from pet_widget import (
    PetWidget, PET_INFO, get_pet_font_family, find_font_file,
    load_selected_pet, save_selected_pet
)
import brain
import main

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

class TestDaisy(unittest.TestCase):
    def setUp(self):
        self.pet = PetWidget()

    def tearDown(self):
        self.pet.close()

    def test_initial_attributes(self):
        self.assertEqual(self.pet.state, "idle")
        self.assertEqual(self.pet.speech_text, "")
        self.assertTrue(hasattr(self.pet, "say"))
        self.assertTrue(hasattr(self.pet, "set_state"))
        self.assertTrue(hasattr(self.pet, "set_pet"))
        self.assertTrue(hasattr(self.pet, "get_current_pet"))
        self.assertTrue(hasattr(self.pet, "on_right_click"))
        self.assertTrue(hasattr(self.pet, "on_double_click"))

    def test_say_and_clear_speech(self):
        self.pet.say("Hello World!", seconds=5)
        self.assertEqual(self.pet.speech_text, "Hello World!")
        self.assertTrue(self.pet._speech_timer.isActive())

        self.pet.clear_speech()
        self.assertEqual(self.pet.speech_text, "")
        self.assertFalse(self.pet._speech_timer.isActive())

    def test_set_state(self):
        for state in ["walk", "jump", "sit", "attack", "throw", "hurt", "idle"]:
            self.pet.set_state(state)
            self.assertEqual(self.pet.state, state)

        # Invalid state defaults to idle
        self.pet.set_state("invalid_state_name")
        self.assertEqual(self.pet.state, "idle")

    def test_animation_update(self):
        # Test idle
        self.pet.set_state("idle")
        f0 = self.pet.frame
        self.pet.update_animation()
        self.assertEqual(self.pet.frame, f0 + 1)

        # Test walk
        self.pet.set_state("walk")
        x0 = self.pet.x()
        self.pet.update_animation()
        self.assertNotEqual(self.pet.x(), x0)

        # Test jump
        self.pet.set_state("jump")
        self.pet.update_animation()
        self.assertTrue(0.0 < self.pet.jump_progress < 1.0)

    def test_paint_event(self):
        # Render each state to ensure no QPainter crashes
        pixmap = QtGui.QPixmap(self.pet.size())
        painter = QtGui.QPainter(pixmap)
        
        for state in ["idle", "walk", "jump", "sit"]:
            self.pet.set_state(state)
            self.pet.say(f"Testing {state}", seconds=10)
            self.pet.paintEvent(QtGui.QPaintEvent(self.pet.rect()))

    def test_mouse_callbacks(self):
        mock_right = MagicMock()
        mock_double = MagicMock()
        self.pet.on_right_click = mock_right
        self.pet.on_double_click = mock_double

        # Simulate right click
        event_right = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPoint(10, 10),
            QtCore.QPoint(100, 100),
            QtCore.Qt.RightButton,
            QtCore.Qt.RightButton,
            QtCore.Qt.NoModifier,
        )
        self.pet.mousePressEvent(event_right)
        mock_right.assert_called_once_with(QtCore.QPoint(100, 100))

        # Simulate double click
        event_double = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonDblClick,
            QtCore.QPoint(10, 10),
            QtCore.QPoint(100, 100),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        self.pet.mouseDoubleClickEvent(event_double)
        mock_double.assert_called_once()

    def test_brain_missing_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("brain.load_api_key", return_value=None):
                with self.assertRaises(brain.BrainError) as ctx:
                    brain.ask("Hi", api_key="")
                self.assertIn("No API key found", str(ctx.exception))

    def test_detect_provider(self):
        self.assertEqual(brain.detect_provider("sk-1234567890"), "openai")
        self.assertEqual(brain.detect_provider("sk-proj-abc123xyz"), "openai")
        self.assertEqual(brain.detect_provider("AIzaSyTestKey123"), "gemini")
        self.assertEqual(brain.detect_provider("gsk_TestKey1234567890"), "groq")
        self.assertEqual(brain.detect_provider("some-random-key"), "gemini")

        with patch.dict(os.environ, {"DAISY_PROVIDER": "openai"}):
            self.assertEqual(brain.detect_provider("AIzaSyTestKey"), "openai")
        with patch.dict(os.environ, {"DAISY_PROVIDER": "gemini"}):
            self.assertEqual(brain.detect_provider("sk-123456789"), "gemini")
        with patch.dict(os.environ, {"DAISY_PROVIDER": "groq"}):
            self.assertEqual(brain.detect_provider("sk-123456789"), "groq")

    def test_brain_key_save_and_load(self):
        with patch.dict(os.environ, {}, clear=True):
            test_key = "AIzaSyTestKey12345"
            saved_path = brain.save_api_key(test_key)
            self.assertTrue(os.path.exists(saved_path))
            loaded = brain.load_api_key()
            self.assertEqual(loaded, test_key)
            masked, provider = brain.get_key_status()
            self.assertEqual(provider, "Gemini")
            self.assertTrue(masked.startswith("AIzaSy"))

            # Test OpenAI key saving
            openai_key = "sk-proj-1234567890abcdef"
            brain.save_api_key(openai_key)
            loaded_openai = brain.load_api_key()
            self.assertEqual(loaded_openai, openai_key)
            masked_oai, provider_oai = brain.get_key_status()
            self.assertEqual(provider_oai, "OpenAI")
            self.assertTrue(masked_oai.startswith("sk-pro"))

            # clean up test key file if created
            key_file = brain.get_key_file_path()
            if os.path.exists(key_file):
                os.remove(key_file)

    def test_brain_openai_ask_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Hello! I am Daisy the desktop pet."
                    }
                }
            ]
        }
        with patch("requests.post", return_value=mock_response):
            answer = brain.ask("Who are you?", api_key="sk-test-key-12345")
            self.assertEqual(answer, "Hello! I am Daisy the desktop pet.")

    def test_brain_openai_ask_errors(self):
        mock_401 = MagicMock()
        mock_401.status_code = 401
        mock_401.json.return_value = {"error": {"message": "Invalid API key"}}
        with patch("requests.post", return_value=mock_401):
            with self.assertRaises(brain.BrainError) as ctx:
                brain.ask("Who are you?", api_key="sk-invalid-key")
            self.assertIn("Invalid OpenAI API key (401)", str(ctx.exception))

        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.json.return_value = {"error": {"message": "Quota exceeded"}}
        with patch("requests.post", return_value=mock_429):
            with self.assertRaises(brain.BrainError) as ctx:
                brain.ask("Who are you?", api_key="sk-quota-key")
            self.assertIn("OpenAI API Quota / Rate limit exceeded (429)", str(ctx.exception))

    def test_brain_groq_ask_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Hello! I am Daisy, running on Groq."
                    }
                }
            ]
        }
        with patch("requests.post", return_value=mock_response):
            answer = brain.ask("Who are you?", api_key="gsk_test_key_12345")
            self.assertEqual(answer, "Hello! I am Daisy, running on Groq.")

    def test_brain_groq_ask_errors(self):
        mock_401 = MagicMock()
        mock_401.status_code = 401
        mock_401.json.return_value = {"error": {"message": "Invalid API key"}}
        with patch("requests.post", return_value=mock_401):
            with self.assertRaises(brain.BrainError) as ctx:
                brain.ask("Who are you?", api_key="gsk_invalid_key")
            self.assertIn("Invalid Groq API key (401)", str(ctx.exception))

        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.json.return_value = {"error": {"message": "Rate limit exceeded"}}
        with patch("requests.post", return_value=mock_429):
            with self.assertRaises(brain.BrainError) as ctx:
                brain.ask("Who are you?", api_key="gsk_quota_key")
            self.assertIn("Groq API Rate limit exceeded (429)", str(ctx.exception))

    def test_brain_gemini_ask_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Hello from Gemini! I'm Daisy."}]
                    }
                }
            ]
        }
        with patch("requests.post", return_value=mock_response):
            answer = brain.ask("Who are you?", api_key="AIzaSyTestKey")
            self.assertEqual(answer, "Hello from Gemini! I'm Daisy.")

    def test_cat_sprite_sheets_loaded(self):
        self.pet.set_pet("cat", save_pref=False)
        self.assertIn("idle", self.pet.sprites)
        self.assertIn("run", self.pet.sprites)
        self.assertIn("jump", self.pet.sprites)
        self.assertIn("fall", self.pet.sprites)
        self.assertIn("idle_left", self.pet.sprites)
        self.assertIn("run_left", self.pet.sprites)
        self.assertIn("jump_left", self.pet.sprites)
        self.assertIn("fall_left", self.pet.sprites)

        self.assertEqual(len(self.pet.sprites["idle"]), 8)
        self.assertEqual(len(self.pet.sprites["run"]), 10)
        self.assertEqual(len(self.pet.sprites["jump"]), 4)
        self.assertEqual(len(self.pet.sprites["fall"]), 4)

    def test_all_pet_types_loading(self):
        """Tests that all 4 pets (cat, pink_monster, owlet_monster, dude_monster) load cleanly."""
        for pet_id in ["cat", "pink_monster", "owlet_monster", "dude_monster"]:
            self.pet.set_pet(pet_id, save_pref=False)
            self.assertEqual(self.pet.get_current_pet(), pet_id)
            self.assertIn("idle", self.pet.sprites)
            self.assertIn("idle_left", self.pet.sprites)
            self.assertIn("jump", self.pet.sprites)
            self.assertTrue(len(self.pet.sprites["idle"]) > 0)
            
            # Check frame rendering
            frame = self.pet._get_current_frame()
            self.assertIsNotNone(frame)
            self.assertFalse(frame.isNull())

            # Check paintEvent doesn't raise errors
            self.pet.paintEvent(QtGui.QPaintEvent(self.pet.rect()))

    def test_monster_animations_and_actions(self):
        """Tests monster-specific animations: attack, throw, hurt, push, death."""
        for monster_id in ["pink_monster", "owlet_monster", "dude_monster"]:
            self.pet.set_pet(monster_id, save_pref=False)
            self.assertIn("attack", self.pet.sprites)
            self.assertIn("throw", self.pet.sprites)
            self.assertIn("hurt", self.pet.sprites)

            # Test Attack Action
            self.pet.set_state("attack")
            self.assertEqual(self.pet.state, "attack")
            frame_attack = self.pet._get_current_frame()
            self.assertIsNotNone(frame_attack)

            # Update animation until attack finishes and returns to idle
            for _ in range(30):
                self.pet.update_animation()
            self.assertEqual(self.pet.state, "idle")

            # Test Throw Action
            self.pet.set_state("throw")
            self.assertEqual(self.pet.state, "throw")
            frame_throw = self.pet._get_current_frame()
            self.assertIsNotNone(frame_throw)

            # Test Hurt
            self.pet.set_state("hurt")
            self.assertEqual(self.pet.state, "hurt")
            frame_hurt = self.pet._get_current_frame()
            self.assertIsNotNone(frame_hurt)

    def test_custom_font_resolution(self):
        font_file = find_font_file()
        self.assertIsNotNone(font_file)
        self.assertTrue(os.path.exists(font_file))
        family = get_pet_font_family()
        self.assertEqual(family, "Planes_ValMore")

    def test_pet_preference_save_load(self):
        save_selected_pet("pink_monster")
        loaded = load_selected_pet()
        self.assertEqual(loaded, "pink_monster")
        # Reset back to cat
        save_selected_pet("cat")
        self.assertEqual(load_selected_pet(), "cat")

    def test_frame_selection(self):
        self.pet.set_pet("cat", save_pref=False)
        # Idle frame
        self.pet.set_state("idle")
        self.pet.walk_dir = 1
        idle_frame = self.pet._get_current_frame()
        self.assertIsNotNone(idle_frame)
        self.assertFalse(idle_frame.isNull())

        # Walk right vs left
        self.pet.set_state("walk")
        self.pet.walk_dir = 1
        walk_r = self.pet._get_current_frame()
        self.pet.walk_dir = -1
        walk_l = self.pet._get_current_frame()
        self.assertIsNotNone(walk_r)
        self.assertIsNotNone(walk_l)

        # Jump: rising vs falling
        self.pet.set_state("jump")
        self.pet.jump_progress = 0.2
        rising_frame = self.pet._get_current_frame()
        self.pet.jump_progress = 0.8
        falling_frame = self.pet._get_current_frame()
        self.assertIsNotNone(rising_frame)
        self.assertIsNotNone(falling_frame)

        # Sit
        self.pet.set_state("sit")
        sit_frame = self.pet._get_current_frame()
        self.assertIsNotNone(sit_frame)

    def test_voice_command_parsing(self):
        import voice

        cmd_run = voice.parse_voice_command("daisy please run faster")
        self.assertEqual(cmd_run["action"], "run")
        self.assertEqual(cmd_run["speed"], 4)

        cmd_walk = voice.parse_voice_command("start walking")
        self.assertEqual(cmd_walk["action"], "walk")
        self.assertEqual(cmd_walk["speed"], 2)

        cmd_jump = voice.parse_voice_command("jump up high")
        self.assertEqual(cmd_jump["action"], "jump")

        cmd_sit = voice.parse_voice_command("please sit down and rest")
        self.assertEqual(cmd_sit["action"], "sit")

        cmd_exit = voice.parse_voice_command("goodbye exit now")
        self.assertEqual(cmd_exit["action"], "exit")

        # Pet Switching Voice Commands
        cmd_pink = voice.parse_voice_command("switch to pink monster")
        self.assertEqual(cmd_pink["action"], "switch_pet")
        self.assertEqual(cmd_pink["pet"], "pink_monster")

        cmd_owlet = voice.parse_voice_command("select owlet monster")
        self.assertEqual(cmd_owlet["action"], "switch_pet")
        self.assertEqual(cmd_owlet["pet"], "owlet_monster")

        cmd_dude = voice.parse_voice_command("change pet to dude monster")
        self.assertEqual(cmd_dude["action"], "switch_pet")
        self.assertEqual(cmd_dude["pet"], "dude_monster")

        cmd_cat = voice.parse_voice_command("switch to cat")
        self.assertEqual(cmd_cat["action"], "switch_pet")
        self.assertEqual(cmd_cat["pet"], "cat")

        # Action Voice Commands
        cmd_attack = voice.parse_voice_command("attack now")
        self.assertEqual(cmd_attack["action"], "attack")

        cmd_throw = voice.parse_voice_command("throw rock")
        self.assertEqual(cmd_throw["action"], "throw")

        cmd_ask = voice.parse_voice_command("what is the largest planet")
        self.assertEqual(cmd_ask["action"], "ask")
        self.assertIn("largest planet", cmd_ask["question"])

    def test_voice_command_execution(self):
        daisy_app = main.DaisyApp()

        # Pet switch command
        daisy_app.execute_voice_command({"action": "switch_pet", "pet": "pink_monster"}, "switch to pink monster")
        self.assertEqual(daisy_app.pet.get_current_pet(), "pink_monster")

        # Attack command
        daisy_app.execute_voice_command({"action": "attack"}, "attack")
        self.assertEqual(daisy_app.pet.state, "attack")

        # Throw command
        daisy_app.execute_voice_command({"action": "throw"}, "throw")
        self.assertEqual(daisy_app.pet.state, "throw")

        # Run command
        daisy_app.execute_voice_command({"action": "run", "speed": 4}, "run")
        self.assertEqual(daisy_app.pet.state, "walk")
        self.assertEqual(daisy_app.pet.walk_speed, 4)

        # Walk command
        daisy_app.execute_voice_command({"action": "walk", "speed": 2}, "walk")
        self.assertEqual(daisy_app.pet.state, "walk")
        self.assertEqual(daisy_app.pet.walk_speed, 2)

        # Jump command
        daisy_app.execute_voice_command({"action": "jump"}, "jump")
        self.assertEqual(daisy_app.pet.state, "jump")

        # Sit command
        daisy_app.execute_voice_command({"action": "sit"}, "sit")
        self.assertEqual(daisy_app.pet.state, "sit")

        # Exit command
        with patch.object(daisy_app.app, "quit") as mock_quit:
            daisy_app.execute_voice_command({"action": "exit"}, "exit")
            self.assertIn("Goodbye", daisy_app.pet.speech_text)

        daisy_app._cleanup()
        daisy_app.pet.close()

    def test_push_to_talk_listener_instantiation(self):
        import voice
        listener = voice.PushToTalkListener()
        self.assertIsNotNone(listener)
        self.assertTrue(hasattr(listener, "started_recording"))
        self.assertTrue(hasattr(listener, "finished_command"))
        self.assertTrue(hasattr(listener, "finished_error"))
        self.assertTrue(hasattr(listener, "stop"))
        listener.stop()

    def test_is_capslock_pressed_callable(self):
        import voice
        result = voice.is_capslock_pressed()
        self.assertIsInstance(result, bool)

    def test_daisy_app_menu_building(self):
        daisy_app = main.DaisyApp()
        menu = daisy_app._build_menu()
        self.assertIsNotNone(menu)
        actions = [a.text() for a in menu.actions() if a.text()]
        self.assertTrue(any("Push-To-Talk" in a or "Voice" in a for a in actions))
        self.assertIn("🐾 Select Pet", actions)
        self.assertIn("Walk", actions)
        self.assertIn("Run", actions)
        self.assertIn("Jump", actions)
        self.assertIn("Sit", actions)
        self.assertIn("Set API Key (Gemini / OpenAI / Groq)...", actions)
        self.assertIn("Quit", actions)

        # Verify Select Pet Submenu
        submenus = [a.menu() for a in menu.actions() if a.menu() is not None]
        self.assertTrue(len(submenus) > 0)
        pet_sub = submenus[0]
        pet_actions = [a.text() for a in pet_sub.actions()]
        self.assertTrue(any("Daisy" in a for a in pet_actions))
        self.assertTrue(any("Pink Monster" in a for a in pet_actions))
        self.assertTrue(any("Owlet Monster" in a for a in pet_actions))
        self.assertTrue(any("Dude Monster" in a for a in pet_actions))

        icon = daisy_app._make_icon()
        self.assertFalse(icon.isNull())
        daisy_app._cleanup()
        daisy_app.pet.close()

    def test_time_of_day_greeting(self):
        from datetime import datetime
        morning_bubble, morning_speech = main.get_time_of_day_greeting(datetime(2026, 8, 15, 8, 0))
        self.assertIn("morning", morning_bubble.lower())
        self.assertNotIn("☀", morning_speech)  # speech text should be emoji-free

        afternoon_bubble, _ = main.get_time_of_day_greeting(datetime(2026, 8, 15, 14, 0))
        self.assertIn("afternoon", afternoon_bubble.lower())

        evening_bubble, _ = main.get_time_of_day_greeting(datetime(2026, 8, 15, 19, 0))
        self.assertIn("evening", evening_bubble.lower())

        night_bubble, _ = main.get_time_of_day_greeting(datetime(2026, 8, 15, 2, 0))
        self.assertIn("late", night_bubble.lower())

    def test_pet_voice_profiles(self):
        import voice
        self.assertIn("cat", voice.PET_VOICE_PROFILES)
        self.assertIn("pink_monster", voice.PET_VOICE_PROFILES)
        self.assertIn("owlet_monster", voice.PET_VOICE_PROFILES)
        self.assertIn("dude_monster", voice.PET_VOICE_PROFILES)

        # Check that each pet has a unique voice profile
        cat_voice = voice.get_voice_for_pet("cat")
        pink_voice = voice.get_voice_for_pet("pink_monster")
        owlet_voice = voice.get_voice_for_pet("owlet_monster")
        dude_voice = voice.get_voice_for_pet("dude_monster")

        self.assertEqual(cat_voice["pet_name"], "Daisy")
        self.assertEqual(pink_voice["pet_name"], "Sakura")
        self.assertEqual(owlet_voice["pet_name"], "Zephyr")
        self.assertEqual(dude_voice["pet_name"], "Ziggy")

        self.assertTrue(cat_voice["voice"].startswith("en-"))
        self.assertTrue(pink_voice["voice"].startswith("en-"))
        self.assertTrue(owlet_voice["voice"].startswith("en-"))
        self.assertTrue(dude_voice["voice"].startswith("en-"))

    def test_pet_aesthetic_voice_commands(self):
        import voice
        cmd_sakura = voice.parse_voice_command("switch to sakura")
        self.assertEqual(cmd_sakura["action"], "switch_pet")
        self.assertEqual(cmd_sakura["pet"], "pink_monster")

        cmd_bubbles = voice.parse_voice_command("choose bubbles")
        self.assertEqual(cmd_bubbles["action"], "switch_pet")
        self.assertEqual(cmd_bubbles["pet"], "pink_monster")

        cmd_zephyr = voice.parse_voice_command("change to zephyr")
        self.assertEqual(cmd_zephyr["action"], "switch_pet")
        self.assertEqual(cmd_zephyr["pet"], "owlet_monster")

        cmd_ziggy = voice.parse_voice_command("select ziggy")
        self.assertEqual(cmd_ziggy["action"], "switch_pet")
        self.assertEqual(cmd_ziggy["pet"], "dude_monster")

    def test_brain_pet_persona(self):
        prompt_daisy = brain.get_system_prompt_for_pet("Daisy (Cat)")
        self.assertIn("You are Daisy", prompt_daisy)

        prompt_sakura = brain.get_system_prompt_for_pet("Sakura (Pink Monster)")
        self.assertIn("You are Sakura", prompt_sakura)

        prompt_zephyr = brain.get_system_prompt_for_pet("Zephyr (Owlet Monster)")
        self.assertIn("You are Zephyr", prompt_zephyr)

        prompt_ziggy = brain.get_system_prompt_for_pet("Ziggy (Dude Monster)")
        self.assertIn("You are Ziggy", prompt_ziggy)

    # ─── Jarvis Engine Tests ────────────────────────────────────────────────

    def test_jarvis_fuzzy_matching(self):
        import jarvis_engine
        match, score = jarvis_engine.fuzzy_best_match("gogle", ["google", "firefox", "spotify"], threshold=70)
        self.assertEqual(match, "google")
        self.assertGreaterEqual(score, 70)

        match_none, _ = jarvis_engine.fuzzy_best_match("nonexistentappnamexyz", ["google", "firefox"], threshold=85)
        self.assertIsNone(match_none)

    def test_jarvis_website_resolver(self):
        import jarvis_engine
        self.assertEqual(jarvis_engine.resolve_website("youtube"), "https://www.youtube.com")
        self.assertEqual(jarvis_engine.resolve_website("github"), "https://github.com")
        self.assertEqual(jarvis_engine.resolve_website("reddit.com"), "https://reddit.com")
        self.assertEqual(jarvis_engine.resolve_website("https://example.com"), "https://example.com")

    def test_jarvis_special_folders(self):
        import jarvis_engine
        self.assertEqual(jarvis_engine.resolve_special_folder("downloads"), "shell:Downloads")
        self.assertEqual(jarvis_engine.resolve_special_folder("documents"), "shell:Personal")
        self.assertEqual(jarvis_engine.resolve_special_folder("desktop"), "shell:Desktop")
        self.assertEqual(jarvis_engine.resolve_special_folder("pictures"), "shell:My Pictures")
        self.assertEqual(jarvis_engine.resolve_special_folder("c drive"), "C:\\")

    def test_jarvis_media_commands(self):
        import jarvis_engine
        with patch("subprocess.Popen") as mock_popen:
            res_vol = jarvis_engine.resolve_media_command("volume up")
            self.assertIsNotNone(res_vol)
            self.assertEqual(res_vol["method"], "Media")
            mock_popen.assert_called_once()

            res_mute = jarvis_engine.resolve_media_command("mute")
            self.assertIsNotNone(res_mute)
            self.assertEqual(res_mute["method"], "Media")

            self.assertIsNone(jarvis_engine.resolve_media_command("something unrelated"))

    def test_jarvis_utility_commands(self):
        import jarvis_engine
        with patch("subprocess.Popen"):
            res_ss = jarvis_engine.resolve_utility_command("take a screenshot")
            self.assertIsNotNone(res_ss)
            self.assertEqual(res_ss["method"], "Utility")

            res_bin = jarvis_engine.resolve_utility_command("empty recycle bin")
            self.assertIsNotNone(res_bin)
            self.assertEqual(res_bin["method"], "Utility")

            res_time = jarvis_engine.resolve_utility_command("what time is it")
            self.assertIsNotNone(res_time)
            self.assertEqual(res_time["method"], "Info")
            self.assertIn("It's", res_time["target"])

            res_date = jarvis_engine.resolve_utility_command("what's today's date")
            self.assertIsNotNone(res_date)
            self.assertEqual(res_date["method"], "Info")
            self.assertIn("Today is", res_date["target"])

    def test_jarvis_system_commands_and_confirmation(self):
        import jarvis_engine
        with patch("subprocess.Popen"):
            # Safe command
            res_lock = jarvis_engine.resolve_system_command("lock screen")
            self.assertIsNotNone(res_lock)
            self.assertEqual(res_lock["method"], "System")

            # Destructive command requires confirmation
            res_shut = jarvis_engine.resolve_system_command("shutdown")
            self.assertIsNotNone(res_shut)
            self.assertEqual(res_shut["method"], "Confirmation")
            self.assertTrue(jarvis_engine.is_pending_confirmation())
            self.assertTrue(jarvis_engine.is_confirm_command("confirm"))

            # Confirming the action executes it
            res_confirm = jarvis_engine.resolve_system_command("confirm")
            self.assertIsNotNone(res_confirm)
            self.assertEqual(res_confirm["method"], "System")
            self.assertFalse(jarvis_engine.is_pending_confirmation())

    def test_jarvis_split_commands(self):
        import jarvis_engine
        parts = jarvis_engine.split_commands("open chrome and open spotify")
        self.assertEqual(parts, ["open chrome", "open spotify"])

        parts_then = jarvis_engine.split_commands("take a screenshot and then open pictures")
        self.assertEqual(parts_then, ["take a screenshot", "open pictures"])

    def test_jarvis_is_jarvis_command(self):
        import jarvis_engine
        self.assertTrue(jarvis_engine.is_jarvis_command("open chrome"))
        self.assertTrue(jarvis_engine.is_jarvis_command("launch spotify"))
        self.assertTrue(jarvis_engine.is_jarvis_command("close notepad"))
        self.assertTrue(jarvis_engine.is_jarvis_command("search python tutorial"))
        self.assertTrue(jarvis_engine.is_jarvis_command("volume up"))
        self.assertTrue(jarvis_engine.is_jarvis_command("take a screenshot"))
        self.assertTrue(jarvis_engine.is_jarvis_command("empty recycle bin"))
        self.assertTrue(jarvis_engine.is_jarvis_command("lock screen"))
        self.assertTrue(jarvis_engine.is_jarvis_command("what time is it"))
        self.assertTrue(jarvis_engine.is_jarvis_command("open my github repo"))

        # General questions should NOT be classified as Jarvis commands
        self.assertFalse(jarvis_engine.is_jarvis_command("why is the sky blue"))
        self.assertFalse(jarvis_engine.is_jarvis_command("tell me a story about a kitten"))

    def test_voice_command_jarvis_routing(self):
        import voice
        cmd_chrome = voice.parse_voice_command("open chrome")
        self.assertEqual(cmd_chrome["action"], "jarvis")

        cmd_search = voice.parse_voice_command("search machine learning")
        self.assertEqual(cmd_search["action"], "jarvis")

        cmd_ss = voice.parse_voice_command("take a screenshot")
        self.assertEqual(cmd_ss["action"], "jarvis")

        cmd_close_spot = voice.parse_voice_command("close spotify")
        self.assertEqual(cmd_close_spot["action"], "jarvis")

        # Questions route to ask
        cmd_ask = voice.parse_voice_command("why do cats purr")
        self.assertEqual(cmd_ask["action"], "ask")

    def test_voice_command_exit_vs_close(self):
        import voice
        cmd_exit = voice.parse_voice_command("exit daisy")
        self.assertEqual(cmd_exit["action"], "exit")

        cmd_quit = voice.parse_voice_command("quit")
        self.assertEqual(cmd_quit["action"], "exit")

        cmd_close_app = voice.parse_voice_command("close chrome")
        self.assertEqual(cmd_close_app["action"], "jarvis")

    def test_jarvis_worker(self):
        import main
        with patch("jarvis_engine.execute_jarvis_command", return_value={"message": "Done!", "results": []}):
            worker = main.JarvisWorker("volume up")
            mock_ok = MagicMock()
            worker.finished_ok.connect(mock_ok)
            worker.run()
            mock_ok.assert_called_once()

    def test_jarvis_config_persistence(self):
        import jarvis_engine
        cfg = jarvis_engine.load_config()
        self.assertIn("user_name", cfg)
        self.assertIn("github_username", cfg)

        cfg["user_name"] = "TestUser"
        jarvis_engine.save_config(cfg)
        loaded = jarvis_engine.load_config()
        self.assertEqual(loaded["user_name"], "TestUser")


if __name__ == "__main__":
    unittest.main()
