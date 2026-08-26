"""
pet_widget.py
The desktop pet body: transparent, frameless, always-on-top window with
sprite sheet animations (idle, walk, jump, sit, attack, throw, etc.) from Animations folder,
multi-pet selection (Daisy Cat, Pink Monster, Owlet Monster, Dude Monster),
custom font rendering (Planes_ValMore), speech bubble, and mouse interaction handlers.
"""

import sys
import os
import math
from typing import Callable, Optional, Dict, List, Any
from PyQt5.QtCore import Qt, QTimer, QRectF, QPoint
from PyQt5.QtGui import (
    QPainter, QColor, QFont, QPen, QPainterPath,
    QPixmap, QTransform, QFontDatabase
)
from PyQt5.QtWidgets import QWidget, QApplication

# ---------------- Pet Metadata & Constants ----------------

PET_INFO: Dict[str, Dict[str, Any]] = {
    "cat": {
        "id": "cat",
        "name": "Daisy (Cat)",
        "icon": "🐱",
        "folder": "FreeCatCharacterAnimations",
        "has_flower": True,
        "actions": ["walk", "run", "jump", "sit"],
        "voice_name": "Daisy (Sweet Kitten 🐱)",
        "aesthetic": "Cottagecore & Cozy",
    },
    "pink_monster": {
        "id": "pink_monster",
        "name": "Sakura (Pink Monster)",
        "icon": "🌸",
        "folder": "1 Pink_Monster",
        "prefix": "Pink_Monster",
        "has_flower": False,
        "actions": ["walk", "run", "jump", "sit", "attack", "throw", "hurt"],
        "voice_name": "Sakura (Cute Fairy Sprite 🌸)",
        "aesthetic": "Pastel & Sweet Fairy",
    },
    "owlet_monster": {
        "id": "owlet_monster",
        "name": "Zephyr (Owlet Monster)",
        "icon": "🦉",
        "folder": "2 Owlet_Monster",
        "prefix": "Owlet_Monster",
        "has_flower": False,
        "actions": ["walk", "run", "jump", "sit", "attack", "throw", "hurt"],
        "voice_name": "Zephyr (Mystic Owlet 🦉)",
        "aesthetic": "Celestial & Mystic Sage",
    },
    "dude_monster": {
        "id": "dude_monster",
        "name": "Ziggy (Dude Monster)",
        "icon": "👾",
        "folder": "3 Dude_Monster",
        "prefix": "Dude_Monster",
        "has_flower": False,
        "actions": ["walk", "run", "jump", "sit", "attack", "throw", "hurt"],
        "voice_name": "Ziggy (Spunky Rascal 👾)",
        "aesthetic": "Retro Arcade & Spunky Rogue",
    },
}

_LOADED_FONT_FAMILY: Optional[str] = None


# ---------------- Font & Preference Helpers ----------------

def find_font_file() -> Optional[str]:
    """Locates the custom Planes_ValMore.ttf font file across execution environments."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    meipass = getattr(sys, "_MEIPASS", "")
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else ""

    candidates = [
        os.path.join(meipass, "Animations", "Font", "Planes_ValMore.ttf") if meipass else "",
        os.path.join(meipass, "Font", "Planes_ValMore.ttf") if meipass else "",
        os.path.join(meipass, "Planes_ValMore.ttf") if meipass else "",
        os.path.join(exe_dir, "Animations", "Font", "Planes_ValMore.ttf") if exe_dir else "",
        os.path.join(exe_dir, "Font", "Planes_ValMore.ttf") if exe_dir else "",
        os.path.join(base_dir, "Animations", "Font", "Planes_ValMore.ttf"),
        os.path.join(base_dir, "Font", "Planes_ValMore.ttf"),
        os.path.join(base_dir, "Planes_ValMore.ttf"),
        os.path.join(os.getcwd(), "Animations", "Font", "Planes_ValMore.ttf"),
        os.path.join(os.getcwd(), "Font", "Planes_ValMore.ttf"),
        os.path.join(os.getcwd(), "Planes_ValMore.ttf"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def get_pet_font_family() -> str:
    """Loads and registers the custom Planes_ValMore font with QFontDatabase, returning its family name."""
    global _LOADED_FONT_FAMILY
    if _LOADED_FONT_FAMILY:
        return _LOADED_FONT_FAMILY

    font_path = find_font_file()
    if font_path and os.path.exists(font_path):
        try:
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    _LOADED_FONT_FAMILY = families[0]
                    return _LOADED_FONT_FAMILY
        except Exception:
            pass

    _LOADED_FONT_FAMILY = "Segoe UI"
    return _LOADED_FONT_FAMILY


def get_config_file_path() -> str:
    """Returns the persistent preference file path for selected pet."""
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
    return os.path.join(base_dir, ".pet_config")


def load_selected_pet() -> str:
    """Loads the user's saved pet choice from file, defaulting to 'cat'."""
    try:
        p = get_config_file_path()
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                val = f.read().strip().lower()
                if val in PET_INFO:
                    return val
    except Exception:
        pass
    return "cat"


def save_selected_pet(pet_id: str) -> bool:
    """Saves the user's selected pet choice to file."""
    try:
        p = get_config_file_path()
        with open(p, "w", encoding="utf-8") as f:
            f.write(pet_id)
        return True
    except Exception:
        return False


def find_animations_dir() -> Optional[str]:
    """Finds the root directory containing animation assets."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    meipass = getattr(sys, "_MEIPASS", "")
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else ""

    candidates = [
        os.path.join(meipass, "Animations") if meipass else "",
        os.path.join(meipass) if meipass else "",
        os.path.join(exe_dir, "Animations") if exe_dir else "",
        os.path.join(exe_dir) if exe_dir else "",
        os.path.join(base_dir, "Animations"),
        os.path.join(base_dir, "animations"),
        os.path.join(base_dir, "animation"),
        os.path.join(base_dir),
        os.path.join(os.getcwd(), "Animations"),
        os.path.join(os.getcwd(), "animations"),
        os.path.join(os.getcwd()),
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            if os.path.isdir(os.path.join(c, "FreeCatCharacterAnimations")) or os.path.isdir(os.path.join(c, "1 Pink_Monster")):
                return c
            if os.path.exists(os.path.join(c, "1_Cat_Idle-Sheet.png")):
                return os.path.dirname(c)
    return None


def find_pet_dir(pet_id: str) -> Optional[str]:
    """Finds the specific animation folder for a given pet."""
    info = PET_INFO.get(pet_id, PET_INFO["cat"])
    folder_name = info["folder"]
    anim_dir = find_animations_dir()
    if anim_dir:
        candidate = os.path.join(anim_dir, folder_name)
        if os.path.isdir(candidate):
            return candidate

    base_dir = os.path.dirname(os.path.abspath(__file__))
    meipass = getattr(sys, "_MEIPASS", "")
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else ""
    direct_candidates = [
        os.path.join(meipass, folder_name) if meipass else "",
        os.path.join(exe_dir, folder_name) if exe_dir else "",
        os.path.join(base_dir, folder_name),
        os.path.join(os.getcwd(), folder_name),
    ]
    for d in direct_candidates:
        if d and os.path.isdir(d):
            return d
    return None


# ---------------- PetWidget Implementation ----------------

class PetWidget(QWidget):
    def __init__(self, brain=None):
        super().__init__()
        self.brain = brain
        self.state: str = "idle"  # idle, walk, jump, sit, attack, throw, hurt, etc.
        self.speech_text: str = ""
        self.frame: int = 0
        self.action_frame: int = 0  # Counter for one-shot action animations

        # Active Pet Choice
        self.current_pet: str = load_selected_pet()

        # Sprite sheets & frame caches
        self.sprites: Dict[str, List[QPixmap]] = {}
        self._load_sprites()

        # Callbacks hooked by main.py
        self.on_right_click: Optional[Callable[[QPoint], None]] = None
        self.on_double_click: Optional[Callable[[], None]] = None
        self.on_middle_click: Optional[Callable[[], None]] = None
        self.on_pet_changed: Optional[Callable[[str], None]] = None

        # Movement and physics
        self.walk_dir: int = 1  # 1 = right, -1 = left
        self.walk_speed: int = 2
        self.jump_progress: float = 0.0  # 0.0 to 1.0
        self.jump_height: int = 45
        self.base_y: Optional[int] = None
        self.drag_pos: QPoint = QPoint()

        # Speech auto-clear timer
        self._speech_timer = QTimer(self)
        self._speech_timer.setSingleShot(True)
        self._speech_timer.timeout.connect(self.clear_speech)

        # Window setup: frameless, transparent, always on top
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Sizing (accommodates speech bubble above and 96x96 sprite below)
        self.pet_size = 96
        self.bubble_height = 100
        self.setFixedSize(280, self.pet_size + self.bubble_height)

        # Animation timer (30 FPS for smooth motion)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(33)

        self.position_at_bottom_right()

    # ---------------- Asset Loading & Multi-Pet ----------------

    def _find_asset_dir(self) -> Optional[str]:
        """Backward-compatible helper returning the Cat animation directory."""
        return find_pet_dir("cat")

    def _slice_sheet(self, sheet_path: str, frame_w: int = 32, frame_h: int = 32) -> List[QPixmap]:
        """Slices a horizontal sprite sheet into individual QPixmap frames."""
        if not sheet_path or not os.path.exists(sheet_path):
            return []
        sheet = QPixmap(sheet_path)
        if sheet.isNull():
            return []
        count = sheet.width() // frame_w
        if count <= 0:
            return []
        return [sheet.copy(i * frame_w, 0, frame_w, frame_h) for i in range(count)]

    def _flip_frames(self, frames: List[QPixmap]) -> List[QPixmap]:
        """Horizontally mirrors a list of frames for left-facing orientation."""
        transform = QTransform().scale(-1, 1)
        return [f.transformed(transform) for f in frames]

    def _load_sprites(self):
        """Loads and prepares sprite frames for the currently active pet."""
        self._load_sprites_for_pet(self.current_pet)

    def _load_sprites_for_pet(self, pet_id: str):
        """Loads and caches all animation frames for the specified pet ID."""
        pet_dir = find_pet_dir(pet_id)
        self.sprites.clear()
        if not pet_dir:
            return

        info = PET_INFO.get(pet_id, PET_INFO["cat"])

        if pet_id == "cat":
            idle_path = os.path.join(pet_dir, "1_Cat_Idle-Sheet.png")
            run_path = os.path.join(pet_dir, "2_Cat_Run-Sheet.png")
            jump_path = os.path.join(pet_dir, "3_Cat_Jump-Sheet.png")
            fall_path = os.path.join(pet_dir, "4_Cat_Fall-Sheet.png")

            idle_frames = self._slice_sheet(idle_path, 32, 32)
            run_frames = self._slice_sheet(run_path, 32, 32)
            jump_frames = self._slice_sheet(jump_path, 32, 32)
            fall_frames = self._slice_sheet(fall_path, 32, 32)

            if idle_frames:
                self.sprites["idle"] = idle_frames
                self.sprites["idle_left"] = self._flip_frames(idle_frames)
            if run_frames:
                self.sprites["run"] = run_frames
                self.sprites["run_left"] = self._flip_frames(run_frames)
                self.sprites["walk"] = run_frames
                self.sprites["walk_left"] = self.sprites["run_left"]
            if jump_frames:
                self.sprites["jump"] = jump_frames
                self.sprites["jump_left"] = self._flip_frames(jump_frames)
            if fall_frames:
                self.sprites["fall"] = fall_frames
                self.sprites["fall_left"] = self._flip_frames(fall_frames)
        else:
            prefix = info.get("prefix", "Pink_Monster")
            idle_path = os.path.join(pet_dir, f"{prefix}_Idle_4.png")
            walk_path = os.path.join(pet_dir, f"{prefix}_Walk_6.png")
            run_path = os.path.join(pet_dir, f"{prefix}_Run_6.png")
            jump_path = os.path.join(pet_dir, f"{prefix}_Jump_8.png")
            attack_path = os.path.join(pet_dir, f"{prefix}_Attack1_4.png")
            attack2_path = os.path.join(pet_dir, f"{prefix}_Attack2_6.png")
            climb_path = os.path.join(pet_dir, f"{prefix}_Climb_4.png")
            death_path = os.path.join(pet_dir, f"{prefix}_Death_8.png")
            hurt_path = os.path.join(pet_dir, f"{prefix}_Hurt_4.png")
            push_path = os.path.join(pet_dir, f"{prefix}_Push_6.png")
            throw_path = os.path.join(pet_dir, f"{prefix}_Throw_4.png")

            idle_frames = self._slice_sheet(idle_path, 32, 32)
            walk_frames = self._slice_sheet(walk_path, 32, 32)
            run_frames = self._slice_sheet(run_path, 32, 32)
            jump_frames = self._slice_sheet(jump_path, 32, 32)
            attack_frames = self._slice_sheet(attack_path, 32, 32) or self._slice_sheet(attack2_path, 32, 32)
            climb_frames = self._slice_sheet(climb_path, 32, 32)
            death_frames = self._slice_sheet(death_path, 32, 32)
            hurt_frames = self._slice_sheet(hurt_path, 32, 32)
            push_frames = self._slice_sheet(push_path, 32, 32)
            throw_frames = self._slice_sheet(throw_path, 32, 32)

            if idle_frames:
                self.sprites["idle"] = idle_frames
                self.sprites["idle_left"] = self._flip_frames(idle_frames)
            if walk_frames:
                self.sprites["walk"] = walk_frames
                self.sprites["walk_left"] = self._flip_frames(walk_frames)
            if run_frames:
                self.sprites["run"] = run_frames
                self.sprites["run_left"] = self._flip_frames(run_frames)
            elif walk_frames:
                self.sprites["run"] = walk_frames
                self.sprites["run_left"] = self.sprites["walk_left"]
            if jump_frames:
                self.sprites["jump"] = jump_frames
                self.sprites["jump_left"] = self._flip_frames(jump_frames)
            if attack_frames:
                self.sprites["attack"] = attack_frames
                self.sprites["attack_left"] = self._flip_frames(attack_frames)
            if climb_frames:
                self.sprites["climb"] = climb_frames
                self.sprites["climb_left"] = self._flip_frames(climb_frames)
            if death_frames:
                self.sprites["death"] = death_frames
                self.sprites["death_left"] = self._flip_frames(death_frames)
            if hurt_frames:
                self.sprites["hurt"] = hurt_frames
                self.sprites["hurt_left"] = self._flip_frames(hurt_frames)
            if push_frames:
                self.sprites["push"] = push_frames
                self.sprites["push_left"] = self._flip_frames(push_frames)
            if throw_frames:
                self.sprites["throw"] = throw_frames
                self.sprites["throw_left"] = self._flip_frames(throw_frames)

    def set_pet(self, pet_id: str, save_pref: bool = True):
        """Switches the active pet character (cat, pink_monster, owlet_monster, dude_monster)."""
        if pet_id not in PET_INFO:
            pet_id = "cat"
        self.current_pet = pet_id
        self._load_sprites_for_pet(pet_id)
        self.state = "idle"
        self.action_frame = 0
        if save_pref:
            save_selected_pet(pet_id)
        if callable(self.on_pet_changed):
            self.on_pet_changed(pet_id)
        self.update()

    def get_current_pet(self) -> str:
        """Returns the ID of the currently active pet."""
        return self.current_pet

    def get_current_pet_name(self) -> str:
        """Returns the display name of the currently active pet."""
        return PET_INFO.get(self.current_pet, {}).get("name", "Daisy")

    @staticmethod
    def get_available_pets() -> Dict[str, Dict[str, Any]]:
        """Returns metadata for all available pets."""
        return PET_INFO

    def position_at_bottom_right(self):
        """Places the pet near the bottom right of the primary screen."""
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.x() + geom.width() - self.width() - 40
            y = geom.y() + geom.height() - self.height() - 40
            self.move(x, y)

    # ---------------- Speech & State Control ----------------

    def say(self, text: str, seconds: int = 10):
        """Displays speech bubble text and clears it automatically after `seconds`."""
        self.speech_text = text
        self._speech_timer.stop()
        if seconds > 0:
            self._speech_timer.start(seconds * 1000)
        self.update()

    def set_speech(self, text: str):
        """Backwards-compatible setter for speech text."""
        self.say(text, seconds=10)

    def clear_speech(self):
        """Hides the speech bubble."""
        self.speech_text = ""
        self._speech_timer.stop()
        self.update()

    def set_state(self, new_state: str, speed: Optional[int] = None):
        """Switches the animation state (idle, walk, jump, sit, attack, throw, hurt, etc.)."""
        valid_states = {
            "idle", "walk", "jump", "sit",
            "attack", "throw", "hurt", "death", "climb", "push"
        }
        if new_state not in valid_states:
            new_state = "idle"

        if speed is not None:
            self.walk_speed = speed
        elif new_state == "walk" and self.walk_speed < 2:
            self.walk_speed = 2

        if new_state == "jump" and self.state != "jump":
            self.jump_progress = 0.0
            self.base_y = self.y()
        elif self.state == "jump" and new_state != "jump" and self.base_y is not None:
            self.move(self.x(), self.base_y)
            self.base_y = None

        if new_state in {"attack", "throw", "hurt", "death", "climb", "push"}:
            self.action_frame = 0

        self.state = new_state
        self.update()

    # ---------------- Animation Loop ----------------

    def update_animation(self):
        self.frame = (self.frame + 1) % 3600

        # State-specific behaviors
        if self.state == "walk":
            screen = QApplication.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
                new_x = self.x() + (self.walk_speed * self.walk_dir)
                # Bounce back from screen boundaries
                if new_x < geom.x() + 10:
                    new_x = geom.x() + 10
                    self.walk_dir = 1
                elif new_x + self.width() > geom.x() + geom.width() - 10:
                    new_x = geom.x() + geom.width() - self.width() - 10
                    self.walk_dir = -1
                self.move(new_x, self.y())

        elif self.state == "jump":
            if self.base_y is None:
                self.base_y = self.y()
            self.jump_progress += 0.05
            if self.jump_progress >= 1.0:
                self.jump_progress = 0.0
                if self.base_y is not None:
                    self.move(self.x(), self.base_y)
                    self.base_y = None
                self.state = "idle"
            else:
                # Parabolic jump arc: 4 * h * t * (1 - t)
                offset = int(4 * self.jump_height * self.jump_progress * (1.0 - self.jump_progress))
                self.move(self.x(), self.base_y - offset)

        elif self.state in {"attack", "throw", "hurt", "death", "climb", "push"}:
            frames = self.sprites.get(self.state, [])
            total_frames = len(frames) if frames else 4
            speed_div = 3
            if self.action_frame >= (total_frames * speed_div):
                self.action_frame = 0
                self.state = "idle"
            else:
                self.action_frame += 1

        self.update()

    # ---------------- Frame Retrieval ----------------

    def _get_current_frame(self) -> Optional[QPixmap]:
        """Returns the appropriate QPixmap frame for the current state, direction, and pet."""
        if not self.sprites:
            return None

        facing_left = (self.walk_dir == -1)
        suffix = "_left" if facing_left else ""

        if self.state == "idle":
            frames = self.sprites.get(f"idle{suffix}", self.sprites.get("idle", []))
            if not frames:
                return None
            idx = (self.frame // 4) % len(frames)
            return frames[idx]

        elif self.state == "walk":
            # For monsters with both walk and run sheets
            if self.walk_speed >= 4 and f"run{suffix}" in self.sprites:
                frames = self.sprites.get(f"run{suffix}", self.sprites.get("run", []))
                step_div = 1
            else:
                frames = self.sprites.get(
                    f"walk{suffix}",
                    self.sprites.get(f"run{suffix}", self.sprites.get("walk", self.sprites.get("run", [])))
                )
                step_div = 2
            if not frames:
                return None
            idx = (self.frame // step_div) % len(frames)
            return frames[idx]

        elif self.state == "jump":
            if "fall" in self.sprites:
                # Cat jump: jump ascending, fall descending
                if self.jump_progress < 0.5:
                    frames = self.sprites.get(f"jump{suffix}", self.sprites.get("jump", []))
                    if not frames:
                        return None
                    norm_p = min(max(self.jump_progress / 0.5, 0.0), 0.999)
                    idx = int(norm_p * len(frames))
                    return frames[idx]
                else:
                    frames = self.sprites.get(f"fall{suffix}", self.sprites.get("fall", []))
                    if not frames:
                        return None
                    norm_p = min(max((self.jump_progress - 0.5) / 0.5, 0.0), 0.999)
                    idx = int(norm_p * len(frames))
                    return frames[idx]
            else:
                # Monster 8-frame jump sequence
                frames = self.sprites.get(f"jump{suffix}", self.sprites.get("jump", []))
                if not frames:
                    return None
                norm_p = min(max(self.jump_progress, 0.0), 0.999)
                idx = int(norm_p * len(frames))
                return frames[idx]

        elif self.state == "sit":
            frames = self.sprites.get(f"idle{suffix}", self.sprites.get("idle", []))
            if not frames:
                return None
            # Relaxed pose
            idx = (self.frame // 8) % min(4, len(frames))
            return frames[idx]

        elif self.state in {"attack", "throw", "hurt", "death", "climb", "push"}:
            frames = self.sprites.get(f"{self.state}{suffix}", self.sprites.get(self.state, []))
            if not frames:
                frames = self.sprites.get(f"idle{suffix}", self.sprites.get("idle", []))
                if not frames:
                    return None
                return frames[0]
            speed_div = 3
            idx = min(self.action_frame // speed_div, len(frames) - 1)
            return frames[idx]

        return None

    # ---------------- Painting ----------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. Speech Bubble
        if self.speech_text:
            self._draw_speech_bubble(painter)

        # 2. Desktop Pet Character
        self._draw_daisy(painter)

    def _draw_speech_bubble(self, painter: QPainter):
        bubble_rect = QRectF(12, 10, self.width() - 24, 76)

        # Shadow
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 30))
        painter.drawRoundedRect(bubble_rect.translated(2, 2), 12, 12)

        # Bubble body
        painter.setPen(QPen(QColor(70, 70, 70), 1.5))
        painter.setBrush(QColor(255, 255, 255, 245))
        painter.drawRoundedRect(bubble_rect, 12, 12)

        # Tail
        tail = QPainterPath()
        tail_x = self.width() / 2
        tail.moveTo(tail_x - 8, bubble_rect.bottom())
        tail.lineTo(tail_x, bubble_rect.bottom() + 10)
        tail.lineTo(tail_x + 8, bubble_rect.bottom())
        painter.drawPath(tail)
        # Cover border seam between bubble and tail
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 245))
        painter.drawRect(QRectF(tail_x - 7, bubble_rect.bottom() - 2, 14, 3))

        # Text with custom Planes_ValMore font
        painter.setPen(QColor(30, 30, 30))
        font_fam = get_pet_font_family()
        font = QFont(font_fam, 9)
        if font_fam == "Segoe UI":
            font.setBold(True)
        painter.setFont(font)
        text_rect = bubble_rect.adjusted(8, 6, -8, -6)
        painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.speech_text)

    def _draw_flower(self, painter: QPainter, x: float, y: float):
        """Draws Daisy's cute signature daisy flower accessory on her head."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        fx = x + (7 if self.walk_dir == 1 else -7)
        fy = y

        # Petals
        painter.setPen(QPen(QColor(210, 210, 210), 1))
        painter.setBrush(QColor(255, 255, 255))
        petal_dist = 4.0
        for i in range(5):
            angle = i * (2 * math.pi / 5)
            px = fx + petal_dist * math.cos(angle)
            py = fy + petal_dist * math.sin(angle)
            painter.drawEllipse(QRectF(px - 2.5, py - 2.5, 5, 5))

        # Flower Center (Yellow)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 215, 0))
        painter.drawEllipse(QRectF(fx - 3, fy - 3, 6, 6))

        painter.restore()

    def _draw_daisy(self, painter: QPainter):
        center_x = self.width() / 2.0
        frame_pixmap = self._get_current_frame()

        if frame_pixmap and not frame_pixmap.isNull():
            target_size = 96
            # Ground shadow beneath character
            painter.save()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 30))
            painter.drawEllipse(QRectF(center_x - 28, self.bubble_height + 84, 56, 10))
            painter.restore()

            # Render pixel art sprite crisply
            painter.save()
            painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
            dest_rect = QRectF(
                center_x - target_size / 2.0,
                self.bubble_height,
                target_size,
                target_size
            )
            painter.drawPixmap(dest_rect.toRect(), frame_pixmap)
            painter.restore()

            # Daisy's signature flower resting on her ear (only for Cat / Daisy)
            info = PET_INFO.get(self.current_pet, {})
            if info.get("has_flower", False):
                flower_y = self.bubble_height + 28
                if self.state == "walk":
                    flower_y += 8
                elif self.state == "jump":
                    flower_y -= 4
                self._draw_flower(painter, center_x, flower_y)
        else:
            self._draw_daisy_procedural(painter)

    def _draw_daisy_procedural(self, painter: QPainter):
        """Fallback procedural renderer if sprite assets cannot be loaded."""
        center_x = self.width() / 2.0
        pet_base_y = self.bubble_height + 45

        scale_x = 1.0
        scale_y = 1.0
        rotation = 0.0
        offset_y = 0.0
        blinking = False

        if self.state == "idle":
            breath = math.sin(self.frame * 0.1)
            scale_y = 1.0 + 0.04 * breath
            scale_x = 1.0 - 0.03 * breath
            blinking = (self.frame % 120) < 6
        elif self.state == "walk":
            step = math.sin(self.frame * 0.3)
            rotation = step * 6.0 * self.walk_dir
            offset_y = -abs(step) * 5.0
            scale_y = 1.0 + 0.03 * math.cos(self.frame * 0.3)
            scale_x = 1.0 - 0.03 * math.cos(self.frame * 0.3)
        elif self.state == "jump":
            if self.jump_progress < 0.2 or self.jump_progress > 0.8:
                scale_y = 0.85
                scale_x = 1.15
            else:
                scale_y = 1.15
                scale_x = 0.9
        elif self.state == "sit":
            scale_y = 0.88
            scale_x = 1.12
            offset_y = 5.0

        painter.save()
        painter.translate(center_x, pet_base_y + offset_y)
        painter.rotate(rotation)
        painter.scale(scale_x, scale_y)

        # Body
        body_color = QColor(146, 208, 132)
        outline_color = QColor(105, 175, 95)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 25))
        painter.drawEllipse(QRectF(-28, 26, 56, 12))

        painter.setPen(QPen(outline_color, 2.5))
        painter.setBrush(body_color)
        painter.drawEllipse(QRectF(-32, -26, 64, 54))

        # Blush
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 140, 160, 140))
        painter.drawEllipse(QRectF(-26, 2, 10, 6))
        painter.drawEllipse(QRectF(16, 2, 10, 6))

        # Eyes
        painter.setBrush(QColor(35, 35, 35))
        painter.setPen(Qt.NoPen)
        if blinking or self.state == "sit":
            painter.setPen(QPen(QColor(35, 35, 35), 2.5, Qt.SolidLine, Qt.RoundCap))
            path_left = QPainterPath()
            path_left.moveTo(-18, 0)
            path_left.quadTo(-13, -4, -8, 0)
            painter.drawPath(path_left)
            path_right = QPainterPath()
            path_right.moveTo(8, 0)
            path_right.quadTo(13, -4, 18, 0)
            painter.drawPath(path_right)
        else:
            painter.drawEllipse(QRectF(-17, -5, 8, 10))
            painter.drawEllipse(QRectF(9, -5, 8, 10))
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(QRectF(-15, -4, 3, 3))
            painter.drawEllipse(QRectF(11, -4, 3, 3))

        # Mouth
        painter.setPen(QPen(QColor(35, 35, 35), 2.0, Qt.SolidLine, Qt.RoundCap))
        smile_path = QPainterPath()
        if self.state == "jump":
            painter.setBrush(QColor(240, 110, 130))
            painter.drawEllipse(QRectF(-4, 5, 8, 8))
        else:
            smile_path.moveTo(-4, 6)
            smile_path.quadTo(0, 9, 4, 6)
            painter.drawPath(smile_path)

        # Flower
        self._draw_flower(painter, 0, -32)

        painter.restore()

    # ---------------- Mouse Events ----------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.RightButton:
            if callable(self.on_right_click):
                self.on_right_click(event.globalPos())
            event.accept()
        elif event.button() == Qt.MidButton:
            if callable(self.on_middle_click):
                self.on_middle_click()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            if callable(self.on_double_click):
                self.on_double_click()
            event.accept()

    def contextMenuEvent(self, event):
        if callable(self.on_right_click):
            self.on_right_click(event.globalPos())
            event.accept()