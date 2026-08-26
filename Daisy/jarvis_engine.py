"""
jarvis_engine.py
Desktop automation engine for Daisy, adapted from J.A.R.V.I.S.

Provides capabilities for:
- Indexing installed Windows applications, Start Menu & Desktop shortcuts, Steam library
- Fuzzy application matching (rapidfuzz with difflib fallback)
- App launching & closing (via taskkill and process matching)
- Website opening & web searching
- Special Windows folders (Downloads, Documents, Desktop, Pictures, Drives, etc.)
- Media & volume controls (SendKeys for Volume Up/Down, Mute, Play/Pause, Next/Previous)
- System utilities (Screenshot to Pictures, Empty Recycle Bin, Time, Date)
- System power actions (Lock Screen, Sleep, Shutdown/Restart with safety confirmation)
- GitHub integration (Open top repository / profile)
- Multi-intent compound command execution ("open chrome and open spotify")
"""

import os
import sys
import time
import json
import re
import random
import threading
import subprocess
import platform
import webbrowser
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

# ─── Environment & Logging Config ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [JarvisEngine] %(message)s",
)
log = logging.getLogger("daisy.jarvis")

# ─── Fuzzy Matching Engine ──────────────────────────────────────────────────
try:
    from rapidfuzz import fuzz as _rf_fuzz, process as _rf_process
    HAVE_RAPIDFUZZ = True
except ImportError:
    HAVE_RAPIDFUZZ = False
    import difflib
    log.info("rapidfuzz not installed — using difflib for fuzzy matching.")


def fuzzy_best_match(query: str, candidates: List[str], threshold: int = 72) -> Tuple[Optional[str], float]:
    """
    Return (best_matching_candidate, score_0_to_100) or (None, best_score_seen)
    if nothing cleared the confidence threshold.
    """
    if not candidates:
        return None, 0.0

    if HAVE_RAPIDFUZZ:
        result = _rf_process.extractOne(query, candidates, scorer=_rf_fuzz.WRatio)
        if result is None:
            return None, 0.0
        match, score, _ = result
        return (match, float(score)) if score >= threshold else (None, float(score))
    else:
        close = difflib.get_close_matches(query, candidates, n=1, cutoff=threshold / 100.0)
        if close:
            ratio = difflib.SequenceMatcher(None, query, close[0]).ratio() * 100.0
            return close[0], ratio
        scores = [(c, difflib.SequenceMatcher(None, query, c).ratio() * 100.0) for c in candidates]
        best = max(scores, key=lambda x: x[1]) if scores else (None, 0.0)
        return None, best[1]


# ─── Config & Persistence ───────────────────────────────────────────────────
def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.resolve()


CONFIG_PATH = _get_base_dir() / "jarvis_config.json"
DEFAULT_CONFIG = {"user_name": "Friend", "github_username": "", "asked_autostart": False}


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return {**DEFAULT_CONFIG, **data}
        except Exception as e:
            log.warning(f"Config read warning: {e}")
    return dict(DEFAULT_CONFIG)


def save_config(cfg: Dict[str, Any]):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning(f"Config save warning: {e}")


CONFIG: Dict[str, Any] = load_config()


# ─── Windows Auto-start ─────────────────────────────────────────────────────
def _startup_folder() -> Path:
    return Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"


def _startup_stub_path() -> Path:
    return _startup_folder() / "Daisy.bat"


def is_autostart_enabled() -> bool:
    if platform.system() != "Windows":
        return False
    return _startup_stub_path().exists()


def enable_autostart():
    if platform.system() != "Windows":
        raise RuntimeError("Auto-start is currently only supported on Windows.")
    folder = _startup_folder()
    if not folder.exists():
        raise RuntimeError(f"Windows Startup folder not found at {folder}.")

    base_dir = _get_base_dir()
    if getattr(sys, "frozen", False):
        launch_line = f'start "" "{sys.executable}"'
    else:
        main_py = base_dir / "main.py"
        launch_line = f'start "" "{sys.executable}" "{main_py}"'

    content = f'@echo off\r\ncd /d "{base_dir}"\r\n{launch_line}\r\n'
    _startup_stub_path().write_text(content, encoding="utf-8")


def disable_autostart():
    stub = _startup_stub_path()
    if stub.exists():
        stub.unlink()


# ─── Windows App & Game Indexer ─────────────────────────────────────────────
INSTALLED_APPS_CACHE: Dict[str, str] = {}
SHORTCUTS_CACHE: Dict[str, Path] = {}
STEAM_GAMES_CACHE: Dict[str, str] = {}  # lowercase game name -> Steam AppID
INDEXING_COMPLETE = threading.Event()
_INDEX_LOCK = threading.Lock()


def _find_steam_install_path() -> Optional[Path]:
    for env_var, subpath in [("PROGRAMFILES(X86)", "Steam"), ("PROGRAMFILES", "Steam")]:
        val = os.environ.get(env_var)
        if val:
            candidate = Path(val) / subpath
            if candidate.exists():
                return candidate
    try:
        import winreg
        for hive, key_path, value_name in [
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        ]:
            try:
                key = winreg.OpenKey(hive, key_path)
                value, _ = winreg.QueryValueEx(key, value_name)
                p = Path(value)
                if p.exists():
                    return p
            except Exception:
                continue
    except ImportError:
        pass
    return None


def _steam_library_folders(steam_path: Path) -> List[Path]:
    libs = [steam_path / "steamapps"]
    vdf_path = steam_path / "steamapps" / "libraryfolders.vdf"
    if vdf_path.exists():
        try:
            text = vdf_path.read_text(errors="ignore")
            for m in re.finditer(r'"path"\s*"([^"]+)"', text):
                lib = Path(m.group(1).replace("\\\\", "\\")) / "steamapps"
                if lib.exists():
                    libs.append(lib)
        except Exception as e:
            log.warning(f"Steam library folder parse warning: {e}")
    return libs


def index_steam_games():
    global STEAM_GAMES_CACHE
    if platform.system() != "Windows":
        return
    steam_path = _find_steam_install_path()
    if not steam_path:
        return
    count = 0
    for lib in _steam_library_folders(steam_path):
        try:
            for manifest in lib.glob("appmanifest_*.acf"):
                try:
                    text = manifest.read_text(errors="ignore")
                    name_m = re.search(r'"name"\s*"([^"]+)"', text)
                    appid_m = re.search(r'"appid"\s*"(\d+)"', text)
                    if name_m and appid_m:
                        STEAM_GAMES_CACHE[name_m.group(1).strip().lower()] = appid_m.group(1)
                        count += 1
                except Exception:
                    continue
        except Exception:
            continue
    log.info(f"Indexed {count} Steam games.")


def index_windows_apps():
    """Index installed Windows applications using PowerShell Get-StartApps, Start Menu
    shortcuts, Desktop shortcuts, and the local Steam game library."""
    global INSTALLED_APPS_CACHE, SHORTCUTS_CACHE
    if platform.system() != "Windows":
        INDEXING_COMPLETE.set()
        return

    with _INDEX_LOCK:
        INDEXING_COMPLETE.clear()
        log.info("Indexing installed Windows applications and shortcuts...")

        try:
            cmd = ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                raw_data = json.loads(res.stdout)
                if isinstance(raw_data, dict):
                    raw_data = [raw_data]

                for item in raw_data:
                    name = item.get("Name", "").strip()
                    appid = item.get("AppID", "").strip()
                    if name and appid:
                        INSTALLED_APPS_CACHE[name.lower()] = appid
                log.info(f"Indexed {len(INSTALLED_APPS_CACHE)} apps via Get-StartApps.")
        except Exception as e:
            log.warning(f"Get-StartApps indexing warning: {e}")

        try:
            shortcut_dirs = [
                Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
                Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
                Path(os.environ.get("USERPROFILE", "")) / "Desktop",
                Path(r"C:\Users\Public\Desktop"),
            ]
            for sdir in shortcut_dirs:
                if not sdir.exists():
                    continue
                pattern = "**/*.lnk" if "Start Menu" in str(sdir) else "*.lnk"
                for lnk in sdir.glob(pattern):
                    SHORTCUTS_CACHE.setdefault(lnk.stem.lower(), lnk)
            log.info(f"Indexed {len(SHORTCUTS_CACHE)} shortcuts.")
        except Exception as e:
            log.warning(f"Shortcut indexing warning: {e}")

        index_steam_games()
        INDEXING_COMPLETE.set()


def start_background_indexing():
    """Starts app indexing in a background daemon thread."""
    t = threading.Thread(target=index_windows_apps, daemon=True)
    t.start()


# ─── Protocols, Websites, and Folders Mappings ──────────────────────────────
KNOWN_PROTOCOLS: Dict[str, str] = {
    "spotify": "spotify:",
    "whatsapp": "whatsapp:",
    "settings": "ms-settings:",
    "system settings": "ms-settings:",
    "chrome": "chrome",
    "edge": "msedge:",
    "firefox": "firefox",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "calculator": "calc",
    "calc": "calc",
    "notepad": "notepad",
    "task manager": "taskmgr",
    "explorer": "explorer",
    "file explorer": "explorer",
    "paint": "mspaint",
    "discord": "discord:",
    "telegram": "tg:",
    "steam": "steam:",
    "zoom": "zoommtg:",
    "browser": "",
}

WEBSITE_MAP: Dict[str, str] = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "google mail": "https://mail.google.com",
    "github": "https://github.com",
    "google maps": "https://maps.google.com",
    "maps": "https://maps.google.com",
    "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com",
    "amazon": "https://www.amazon.com",
    "netflix": "https://www.netflix.com",
    "reddit": "https://www.reddit.com",
    "twitter": "https://www.twitter.com",
    "x": "https://www.x.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "linkedin": "https://www.linkedin.com",
    "wikipedia": "https://www.wikipedia.org",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
    "whatsapp web": "https://web.whatsapp.com",
    "translate": "https://translate.google.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
}

DOMAIN_PATTERN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+(/\S*)?$", re.IGNORECASE)
WIN_PATH_PATTERN = re.compile(r"^[a-zA-Z]:\\|^\\\\")
UNIX_PATH_PATTERN = re.compile(r"^/[^ ]+")

SPECIAL_FOLDERS: Dict[str, str] = {
    "downloads": "shell:Downloads",
    "download": "shell:Downloads",
    "documents": "shell:Personal",
    "my documents": "shell:Personal",
    "desktop": "shell:Desktop",
    "pictures": "shell:My Pictures",
    "photos": "shell:My Pictures",
    "music": "shell:My Music",
    "videos": "shell:My Video",
    "this pc": "shell:MyComputerFolder",
    "my computer": "shell:MyComputerFolder",
    "recycle bin": "shell:RecycleBinFolder",
    "control panel": "shell:ControlPanelFolder",
    "appdata": "shell:AppData",
    "home folder": "shell:Profile",
    "home": "shell:Profile",
}
DRIVE_PATTERN = re.compile(r"^([a-z])\s*(?::)?\s*drive$", re.IGNORECASE)


def resolve_special_folder(query: str) -> Optional[str]:
    """Return a shell: alias or drive path if the query names a well-known folder."""
    q = query.strip().lower()
    q_nofolder = re.sub(r"\s+folder$", "", q).strip()
    for key in (q, q_nofolder):
        if key in SPECIAL_FOLDERS:
            return SPECIAL_FOLDERS[key]
    m = DRIVE_PATTERN.match(q_nofolder) or DRIVE_PATTERN.match(q)
    if m:
        return f"{m.group(1).upper()}:\\"
    return None


def search_named_folder(name: str) -> Optional[Path]:
    """Fuzzy-search common folders (Desktop, Documents, Downloads, home dir) for subfolder."""
    home = Path.home()
    roots = [home / "Desktop", home / "Documents", home / "Downloads", home]
    candidates: Dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        try:
            for entry in root.iterdir():
                if entry.is_dir():
                    candidates.setdefault(entry.name.lower(), entry)
        except Exception:
            continue
    if not candidates:
        return None
    match, score = fuzzy_best_match(name, list(candidates.keys()), threshold=72)
    return candidates[match] if match else None


def open_folder(target: str) -> Dict[str, Any]:
    try:
        subprocess.Popen(["explorer.exe", target])
        return {"method": "Folder", "target": target}
    except Exception as e:
        raise RuntimeError(f"Found folder '{target}' but couldn't open it ({e}).")


# ─── Process Terminator ─────────────────────────────────────────────────────
CLOSE_VERBS = ("close ", "quit ", "kill ", "exit ", "stop ")


def _list_running_processes() -> List[str]:
    """Return list of running process names (e.g. 'chrome.exe')."""
    res = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=8)
    names = []
    for line in res.stdout.strip().splitlines():
        parts = line.split('","')
        if parts:
            names.append(parts[0].strip('"'))
    return names


def close_app(query: str) -> Dict[str, Any]:
    """Close a running app by fuzzy-matched name via taskkill."""
    if platform.system() != "Windows":
        raise RuntimeError("Closing apps by name is currently only supported on Windows.")

    running = _list_running_processes()
    if not running:
        raise RuntimeError("No running processes could be read.")

    query = query.strip().lower()
    guess = f"{query}.exe"
    match_name = next((p for p in running if p.lower() == guess), None)

    if not match_name:
        stripped = {p: (p[:-4] if p.lower().endswith(".exe") else p) for p in running}
        best, score = fuzzy_best_match(query, list(stripped.values()), threshold=72)
        if best:
            match_name = next((p for p, s in stripped.items() if s == best), None)

    if not match_name:
        raise RuntimeError(f"'{query}' doesn't seem to be running right now.")

    try:
        subprocess.run(["taskkill", "/IM", match_name, "/F"], capture_output=True, text=True, timeout=8)
        return {"method": "Close", "target": match_name}
    except Exception as e:
        raise RuntimeError(f"Found '{match_name}' running but couldn't close it ({e}).")


# ─── System Power Actions & Confirmation ────────────────────────────────────
SAFE_SYSTEM_ACTIONS: Dict[str, Tuple[str, List[str]]] = {
    "lock": ("Screen locked.", ["rundll32.exe", "user32.dll,LockWorkStation"]),
    "lock screen": ("Screen locked.", ["rundll32.exe", "user32.dll,LockWorkStation"]),
    "lock the screen": ("Screen locked.", ["rundll32.exe", "user32.dll,LockWorkStation"]),
    "sleep": ("Putting the computer to sleep.", ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]),
    "go to sleep": ("Putting the computer to sleep.", ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]),
    "cancel shutdown": ("Shutdown cancelled.", ["shutdown", "/a"]),
    "abort shutdown": ("Shutdown cancelled.", ["shutdown", "/a"]),
}

DESTRUCTIVE_ACTIONS: Dict[str, Tuple[str, List[str]]] = {
    "shutdown": ("shut down the computer", ["shutdown", "/s", "/t", "5"]),
    "shut down": ("shut down the computer", ["shutdown", "/s", "/t", "5"]),
    "shut down the computer": ("shut down the computer", ["shutdown", "/s", "/t", "5"]),
    "turn off the computer": ("shut down the computer", ["shutdown", "/s", "/t", "5"]),
    "restart": ("restart the computer", ["shutdown", "/r", "/t", "5"]),
    "reboot": ("restart the computer", ["shutdown", "/r", "/t", "5"]),
    "restart the computer": ("restart the computer", ["shutdown", "/r", "/t", "5"]),
    "log off": ("log off", ["shutdown", "/l"]),
    "sign out": ("log off", ["shutdown", "/l"]),
}

CONFIRM_PHRASES = ("yes", "confirm", "yes confirm", "confirm it", "do it", "yes shutdown", "yes restart", "sure")
_PENDING_CONFIRMATION: Dict[str, float] = {}
_CONFIRMATION_WINDOW_SECONDS = 20


def is_pending_confirmation() -> bool:
    now = time.time()
    for _, expiry in list(_PENDING_CONFIRMATION.items()):
        if now < expiry:
            return True
    return False


def is_confirm_command(query: str) -> bool:
    q = query.strip().lower().strip(".!?")
    return q in CONFIRM_PHRASES and is_pending_confirmation()


def resolve_system_command(raw_query: str) -> Optional[Dict[str, Any]]:
    q = raw_query.strip().lower().strip(".!?")

    if q in CONFIRM_PHRASES:
        now = time.time()
        for action, expiry in list(_PENDING_CONFIRMATION.items()):
            if now < expiry:
                label, cmd = DESTRUCTIVE_ACTIONS[action]
                _PENDING_CONFIRMATION.clear()
                try:
                    subprocess.Popen(cmd)
                except Exception as e:
                    raise RuntimeError(f"Confirmed, but couldn't {label} ({e}).")
                return {"method": "System", "target": label}
        return None

    if q in SAFE_SYSTEM_ACTIONS:
        label, cmd = SAFE_SYSTEM_ACTIONS[q]
        try:
            subprocess.Popen(cmd)
        except Exception as e:
            raise RuntimeError(f"Couldn't execute command ({e}).")
        return {"method": "System", "target": label}

    if q in DESTRUCTIVE_ACTIONS:
        label, _ = DESTRUCTIVE_ACTIONS[q]
        _PENDING_CONFIRMATION.clear()
        _PENDING_CONFIRMATION[q] = time.time() + _CONFIRMATION_WINDOW_SECONDS
        return {
            "method": "Confirmation",
            "target": f"Say 'confirm' within {_CONFIRMATION_WINDOW_SECONDS} seconds to {label}.",
            "action": q,
        }

    return None


# ─── Media Controls ─────────────────────────────────────────────────────────
MEDIA_KEY_COMMANDS: Dict[str, str] = {
    "mute": "[char]173",
    "unmute": "[char]173",
    "volume up": "[char]175",
    "increase volume": "[char]175",
    "louder": "[char]175",
    "volume down": "[char]174",
    "decrease volume": "[char]174",
    "quieter": "[char]174",
    "play": "[char]179",
    "pause": "[char]179",
    "play music": "[char]179",
    "pause music": "[char]179",
    "play pause": "[char]179",
    "next track": "[char]176",
    "next song": "[char]176",
    "skip track": "[char]176",
    "skip song": "[char]176",
    "previous track": "[char]177",
    "previous song": "[char]177",
}


def resolve_media_command(raw_query: str) -> Optional[Dict[str, Any]]:
    q = raw_query.strip().lower().strip(".!?")
    key_expr = MEDIA_KEY_COMMANDS.get(q)
    if key_expr is None:
        return None
    try:
        subprocess.Popen([
            "powershell", "-NoProfile", "-Command",
            f"(New-Object -ComObject WScript.Shell).SendKeys({key_expr})",
        ])
    except Exception as e:
        raise RuntimeError(f"Couldn't send media command ({e}).")
    return {"method": "Media", "target": q}


# ─── Utilities (Screenshot, Trash, Time, Date) ──────────────────────────────
_SCREENSHOT_PS = (
    "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
    "$s=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
    "$bmp=New-Object System.Drawing.Bitmap $s.Width,$s.Height; "
    "$g=[System.Drawing.Graphics]::FromImage($bmp); "
    "$g.CopyFromScreen($s.Location,[System.Drawing.Point]::Empty,$s.Size); "
    "$p=\"$env:USERPROFILE\\Pictures\\Daisy_Screenshot_$(Get-Date -Format yyyyMMdd_HHmmss).png\"; "
    "$bmp.Save($p)"
)


def resolve_utility_command(raw_query: str) -> Optional[Dict[str, Any]]:
    q = raw_query.strip().lower().strip(".!?")
    if q in ("take a screenshot", "screenshot", "take screenshot", "capture screen", "screen capture"):
        try:
            subprocess.Popen(["powershell", "-NoProfile", "-Command", _SCREENSHOT_PS])
        except Exception as e:
            raise RuntimeError(f"Couldn't take a screenshot ({e}).")
        return {"method": "Utility", "target": "Screenshot saved to your Pictures folder 📸"}

    if q in ("empty recycle bin", "empty the recycle bin", "empty trash", "clean recycle bin"):
        try:
            subprocess.Popen(["powershell", "-NoProfile", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"])
        except Exception as e:
            raise RuntimeError(f"Couldn't empty the recycle bin ({e}).")
        return {"method": "Utility", "target": "Recycle bin emptied 🗑️"}

    if q in ("what time is it", "what's the time", "whats the time", "current time", "tell me the time", "time now"):
        return {"method": "Info", "target": time.strftime("It's %I:%M %p").lstrip("0")}

    if q in ("what's the date", "what is the date", "whats the date", "what's today's date", "today's date", "current date"):
        return {"method": "Info", "target": time.strftime("Today is %A, %B %d, %Y")}

    return None


# ─── GitHub Integration ─────────────────────────────────────────────────────
def is_github_intent(query: str) -> bool:
    q = query.lower()
    return "github" in q and ("repo" in q or "profile" in q or "my github" in q or "account" in q)


def resolve_github_intent(query: str) -> Dict[str, Any]:
    username = (CONFIG.get("github_username") or "").strip()
    if not username:
        raise RuntimeError("GitHub username is not set. Right-click Daisy -> Jarvis Settings to set it!")

    if "profile" in query and "repo" not in query:
        return open_website(f"https://github.com/{username}")

    import requests
    api_url = f"https://api.github.com/users/{username}/repos?per_page=100&sort=updated"
    try:
        resp = requests.get(api_url, timeout=6, headers={"Accept": "application/vnd.github+json"})
    except Exception as e:
        raise RuntimeError(f"Couldn't connect to GitHub ({e}).")

    if resp.status_code == 404:
        raise RuntimeError(f"GitHub user '{username}' was not found.")
    if resp.status_code == 403:
        raise RuntimeError("GitHub API rate limit reached. Try again in a few minutes.")
    if not resp.ok:
        raise RuntimeError(f"GitHub API returned error {resp.status_code}.")

    repos = resp.json()
    if not repos:
        raise RuntimeError(f"User '{username}' has no public repositories.")

    top = max(repos, key=lambda r: r.get("stargazers_count", 0))
    return open_website(top["html_url"])


# ─── Website Resolver ───────────────────────────────────────────────────────
def resolve_website(query: str) -> Optional[str]:
    if query in WEBSITE_MAP:
        return WEBSITE_MAP[query]

    words = query.split()
    for name, url in WEBSITE_MAP.items():
        name_words = name.split()
        if len(name_words) == 1:
            if name in words:
                return url
        else:
            padded = f" {query} "
            if f" {name} " in padded or query == name:
                return url

    if query.startswith("http://") or query.startswith("https://"):
        return query
    if DOMAIN_PATTERN.match(query.replace(" ", "")):
        candidate = query.replace(" ", "")
        return candidate if candidate.startswith("http") else f"https://{candidate}"

    fuzzy_candidates = [name for name in WEBSITE_MAP if len(name) > 3]
    match, score = fuzzy_best_match(query, fuzzy_candidates, threshold=82)
    if match:
        return WEBSITE_MAP[match]
    return None


def open_website(url: str) -> Dict[str, Any]:
    def _open():
        try:
            webbrowser.open(url, new=2)
        except Exception as e:
            log.warning(f"Website open error '{url}': {e}")

    threading.Thread(target=_open, daemon=True).start()
    return {"method": "Website", "target": url}


# ─── Native App Launcher ────────────────────────────────────────────────────
LEADING_VERBS = ("please ", "open ", "launch ", "run ", "start ", "play ", "go to ", "search ")
WAKE_PHRASES = ("hey daisy", "hello daisy", "ok daisy", "daisy", "hey jarvis", "jarvis")
SPLIT_PATTERN = re.compile(r"\s*,\s*|\s+and then\s+|\s+then\s+|\s+and also\s+|\s+and\s+", re.IGNORECASE)
_LEADING_CONNECTOR = re.compile(r"^(then|also|and)\s+", re.IGNORECASE)


def split_commands(text: str) -> List[str]:
    raw_parts = [p.strip() for p in SPLIT_PATTERN.split(text) if p.strip()]
    parts = []
    for p in raw_parts:
        cleaned = _LEADING_CONNECTOR.sub("", p).strip()
        if cleaned:
            parts.append(cleaned)
    return parts or [text.strip()]


def strip_wake_phrase(text: str) -> str:
    t = text.strip().lower()
    for phrase in WAKE_PHRASES:
        if t.startswith(phrase):
            t = t[len(phrase):].strip(" ,.!")
    return t


def strip_leading_verb(query: str) -> str:
    q = query.strip().lower()
    changed = True
    while changed:
        changed = False
        for prefix in LEADING_VERBS:
            if q.startswith(prefix):
                q = q[len(prefix):].strip()
                changed = True
    return q


def launch_windows_app(query: str) -> Dict[str, Any]:
    log.info(f"Launching Windows app for: '{query}'")

    candidates: Dict[str, Tuple[str, Any]] = {}
    for name, appid in INSTALLED_APPS_CACHE.items():
        candidates[name] = ("app", appid)
    for name, path in SHORTCUTS_CACHE.items():
        candidates.setdefault(name, ("shortcut", path))
    for name, appid in STEAM_GAMES_CACHE.items():
        candidates[name] = ("steam", appid)

    match_name: Optional[str] = None
    match_score = 100.0

    if query in candidates:
        match_name = query
    else:
        for name in candidates:
            if query == name:
                match_name = name
                break
            if len(name) >= 3 and re.search(rf"\b{re.escape(name)}\b", query):
                match_name = name
                break
            if len(query) >= 3 and query in name:
                match_name = name
                break

    if not match_name and candidates:
        best, score = fuzzy_best_match(query, list(candidates.keys()), threshold=72)
        if best:
            match_name, match_score = best, score

    if match_name:
        kind, payload = candidates[match_name]
        try:
            if kind == "app":
                subprocess.Popen(f'explorer.exe shell:AppsFolder\\{payload}', shell=True)
                method = "AppID" if match_score >= 99 else f"AppID (fuzzy match, {match_score:.0f}%)"
                return {"method": method, "target": match_name, "appid": payload}
            elif kind == "steam":
                subprocess.Popen(["cmd", "/c", "start", "", f"steam://rungameid/{payload}"])
                method = "Steam" if match_score >= 99 else f"Steam (fuzzy match, {match_score:.0f}%)"
                return {"method": method, "target": match_name, "appid": payload}
            else:
                subprocess.Popen(["cmd", "/c", "start", "", str(payload)])
                method = "Shortcut" if match_score >= 99 else f"Shortcut (fuzzy match, {match_score:.0f}%)"
                return {"method": method, "target": match_name}
        except Exception as e:
            raise RuntimeError(f"Found '{match_name}' but couldn't launch it ({e}).")

    proto = KNOWN_PROTOCOLS.get(query)
    if proto is None:
        for k, v in KNOWN_PROTOCOLS.items():
            if k in query or query in k:
                proto = v
                break

    if proto is not None:
        try:
            if proto == "":
                return open_website("about:blank")
            subprocess.Popen(["cmd", "/c", "start", "", proto])
            return {"method": "Protocol", "target": proto}
        except Exception as e:
            log.warning(f"Protocol launch failed: {e}")

    if (WIN_PATH_PATTERN.match(query) or UNIX_PATH_PATTERN.match(query)) and Path(query).exists():
        try:
            subprocess.Popen(["cmd", "/c", "start", "", query])
            return {"method": "Path", "target": query}
        except Exception as e:
            raise RuntimeError(f"Found file '{query}' but couldn't open it ({e}).")

    folder_query = re.sub(r"\s+folder$", "", query).strip()
    found_folder = search_named_folder(folder_query or query)
    if found_folder:
        return open_folder(str(found_folder))

    raise RuntimeError(f"Couldn't find '{query}' in installed apps, shortcuts, or Steam library.")


def launch_native_app(query: str) -> Dict[str, Any]:
    system = platform.system()
    if system == "Windows":
        return launch_windows_app(query)
    elif system == "Darwin":
        try:
            subprocess.run(["open", "-a", query], check=True, capture_output=True, timeout=5)
            return {"method": "macOS open", "target": query}
        except Exception:
            raise RuntimeError(f"Couldn't find '{query}' on macOS.")
    else:
        try:
            subprocess.run(["xdg-open", query], check=True, capture_output=True, timeout=5)
            return {"method": "Linux xdg-open", "target": query}
        except Exception:
            raise RuntimeError(f"Couldn't find '{query}' on Linux.")


# ─── Single & Multi Command Resolution ──────────────────────────────────────
def resolve_single_command(raw: str) -> Dict[str, Any]:
    raw_wake_stripped = strip_wake_phrase(raw)
    lowered = raw_wake_stripped.strip().lower()

    # 1. Close-app verbs
    for verb in CLOSE_VERBS:
        if lowered.startswith(verb):
            target = lowered[len(verb):].strip()
            if target and target != "daisy":
                return close_app(target)

    # 2. System power & confirmation
    if platform.system() == "Windows":
        sys_result = resolve_system_command(lowered)
        if sys_result:
            return sys_result
        media_result = resolve_media_command(lowered)
        if media_result:
            return media_result

    # 3. Utilities (screenshot, trash, time, date)
    util_result = resolve_utility_command(lowered)
    if util_result:
        return util_result

    # 4. Search query
    search_match = re.match(r"^(?:search(?: for)?|google)\s+(.+)$", lowered)
    if search_match:
        search_term = search_match.group(1).strip()
        if search_term:
            import urllib.parse
            return open_website(f"https://www.google.com/search?q={urllib.parse.quote(search_term)}")

    query = strip_leading_verb(raw_wake_stripped)
    if not query:
        raise RuntimeError("Empty command.")

    # 5. GitHub intent
    if is_github_intent(query):
        return resolve_github_intent(query)

    # 6. Website
    url = resolve_website(query)
    if url:
        return open_website(url)

    if query == "browser":
        return open_website("about:blank")

    # 7. Special Windows folder
    if platform.system() == "Windows":
        folder_target = resolve_special_folder(query)
        if folder_target:
            return open_folder(folder_target)

    # 8. Native app / shortcut / Steam
    return launch_native_app(query)


def execute_jarvis_command(command_text: str) -> Dict[str, Any]:
    """
    Parse a natural-language utterance that may contain multiple commands
    and execute each in sequence, returning formatted spoken/written messages.
    """
    sub_commands = split_commands(command_text)
    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    for sub in sub_commands:
        try:
            results.append(resolve_single_command(sub))
        except Exception as e:
            errors.append(str(e))

    if not results and errors:
        raise RuntimeError(" ".join(errors))

    messages = []
    for r in results:
        method = r.get("method", "")
        target = r.get("target", "") or ""
        if method == "Confirmation":
            messages.append(target)
        elif method == "Info":
            messages.append(target)
        elif method == "Close":
            messages.append(f"Closed {target}")
        elif method == "System":
            messages.append(target[0].upper() + target[1:] if target else "Done.")
        elif method == "Media":
            messages.append(target.title())
        elif method == "Utility":
            messages.append(target)
        elif method == "Folder":
            folder_name = target.replace("shell:", "").replace("Folder", "").replace("My ", "")
            if "Personal" in folder_name:
                folder_name = "Documents"
            messages.append(f"Opening {folder_name.title()} folder 📁")
        elif method == "Website":
            # Clean display for websites
            clean = target.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
            if "google.com/search?q=" in target:
                messages.append("Searching Google...")
            else:
                messages.append(f"Opening {clean.capitalize()}")
        else:
            messages.append(f"Opening {target.title()}" if target else "Done.")

    combined_msg = "; ".join(messages) or "Done!"
    if errors:
        combined_msg += f" (Note: {' '.join(errors)})"

    return {
        "success": True,
        "message": combined_msg,
        "results": results,
        "errors": errors,
    }


# ─── Intent Detector: Is this a Jarvis Desktop Automation Command? ─────────
def is_jarvis_command(text: str) -> bool:
    """
    Determines if an input string is an actionable Jarvis PC automation command
    (app launch, close app, web search, website, media key, system action, etc.)
    rather than a general AI pet question.
    """
    if not text:
        return False

    t = strip_wake_phrase(text).strip().lower()
    if not t:
        return False

    # Pending confirmation phrase ("confirm", "yes")
    if is_confirm_command(t):
        return True

    # Closing apps (e.g. "close spotify", "quit chrome", "kill notepad")
    for verb in CLOSE_VERBS:
        if t.startswith(verb):
            rem = t[len(verb):].strip()
            if rem and rem not in ("daisy", "pet", "program", "app"):
                return True

    # System actions (lock, sleep, shutdown, restart, abort shutdown)
    if t in SAFE_SYSTEM_ACTIONS or t in DESTRUCTIVE_ACTIONS:
        return True

    # Media controls (volume up, mute, next song, play, pause)
    if t in MEDIA_KEY_COMMANDS:
        return True

    # Utilities (screenshot, empty recycle bin, time, date)
    if t in (
        "take a screenshot", "screenshot", "take screenshot", "capture screen",
        "empty recycle bin", "empty the recycle bin", "empty trash",
        "what time is it", "what's the time", "whats the time", "current time", "tell me the time",
        "what's the date", "what is the date", "whats the date", "what's today's date", "today's date",
    ):
        return True

    # Web search
    if re.match(r"^(?:search(?: for)?|google)\s+(.+)$", t):
        return True

    # GitHub commands
    if is_github_intent(t):
        return True

    # Launch verbs (open, launch, run, start, go to)
    for verb in ("open ", "launch ", "run ", "start ", "go to "):
        if t.startswith(verb):
            rem = t[len(verb):].strip()
            if rem:
                return True

    # Direct website or special folder names
    if t in WEBSITE_MAP or t in SPECIAL_FOLDERS or DRIVE_PATTERN.match(t):
        return True

    # Known protocols
    if t in KNOWN_PROTOCOLS:
        return True

    # Compound commands containing "and open", "and then open", etc.
    if re.search(r"\b(and then|and also|and)\s+(open|launch|run|close|search)\b", t):
        return True

    return False
