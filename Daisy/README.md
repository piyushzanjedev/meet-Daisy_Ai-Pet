# Daisy — AI Desktop Pet

A small green blob with a flower on her head who lives on your desktop,
walks/jumps around, and answers questions using OpenAI, Google's Gemini API,
or Groq (free, no credit card required).

## 1. Install Python dependencies

Open a terminal in this folder and run:

```
python -m venv venv
venv\Scripts\activate        (Windows)
source venv/bin/activate     (macOS/Linux)

pip install -r requirements.txt
```

## 2. Get an API key (Choose Gemini, Groq, or OpenAI)

Daisy supports Google Gemini, Groq, and OpenAI:

* **Groq (Free, no card, no billing setup, recommended if Gemini gives you trouble)**:
  1. Go to https://console.groq.com/keys
  2. Sign in and click "Create API Key" — 100% free, no credit card, no billing configuration required.
  3. Runs fast open models (Llama 3.3, etc.) via an OpenAI-compatible endpoint.
* **Google Gemini (Free)**:
  1. Go to https://aistudio.google.com/apikey
  2. Sign in with a Google account and click "Create API key" — no credit card needed, though some
     free-tier projects can occasionally hit a Google-side access review (a 403 "project denied access"
     error). If that happens, Groq is a reliable fallback that doesn't use Google's project/billing system.
* **OpenAI**:
  1. Go to https://platform.openai.com/api-keys
  2. Create a secret key (`sk-...`). Note: OpenAI requires a payment method on file in your account
     billing settings before API calls will work, even for the cheapest model.

## 3. Set the key

You can set your API key in any of these ways:

**Option A: Directly in Daisy's UI (Easiest)**
* Right-click Daisy on your desktop, click **"Set API Key (Gemini / OpenAI / Groq)..."**, paste your key, and click OK. Daisy automatically detects whether you provided a Gemini, OpenAI, or Groq key!

**Option B: As an Environment Variable**
* **Windows (permanent):**
  ```
  setx GEMINI_API_KEY "your-gemini-key-here"
  # or
  setx GROQ_API_KEY "your-gsk-key-here"
  # or
  setx OPENAI_API_KEY "your-sk-key-here"
  ```
* **macOS/Linux:**
  ```
  export GEMINI_API_KEY="your-gemini-key-here"
  # or
  export GROQ_API_KEY="your-gsk-key-here"
  # or
  export OPENAI_API_KEY="your-sk-key-here"
  ```

## 4. Run Daisy

```
python main.py
```

She'll appear near the bottom of your screen.

## Controls & Voice Commands

- **Hold CapsLock (Push-To-Talk)** — **Hold CapsLock** anywhere, speak your command, and **release CapsLock**!
- **Middle-click** — instant shortcut to trigger Voice Command listening
- **Right-click** — open her menu (Voice Command / Walk / Run / Jump / Sit / Ask / Set Key / Quit)
- **Left-click + drag** — move Daisy anywhere on screen
- **Double-click** — quick way to ask her a question by typing
- **System tray icon** — same menu, if you close her window accidentally

### Voice Commands Supported (Push-To-Talk)
Hold **CapsLock**, speak, and release:
- 🏃 **"Run"** / "Run faster" / "Sprint" — Daisy runs fast across the screen
- 🐾 **"Walk"** / "Go" / "Move" — Daisy walks at normal speed
- 🐱 **"Jump"** / "Hop" / "Bounce" — Daisy leaps in an arc
- 💤 **"Sit"** / "Rest" / "Stop" / "Freeze" — Daisy sits down and relaxes
- 👋 **"Exit"** / "Quit" / "Close Daisy" / "Goodbye" — Daisy says goodbye and exits
- 💬 **"Ask [question]"** / "Daisy [question]" / "What is..." — Daisy answers with her AI brain and speaks back in her cute voice!

### ⚡ Jarvis PC Automation Commands (Voice or Text)
Daisy has a full **Jarvis Desktop Automation Engine** built-in! Say or type:
- 🚀 **App Launching**: "Open Chrome", "Launch Spotify", "Open VS Code", "Open Calculator", "Play Cyberpunk", "Open Notepad"
- 🌐 **Websites & Search**: "Open YouTube", "Go to Reddit", "Open GitHub", "Search Python tutorials", "Google latest AI news"
- 📁 **Special Folders**: "Open Downloads", "Open Documents", "Open Desktop", "Open Pictures", "Open C drive"
- 🎵 **Media & Volume**: "Volume up", "Volume down", "Mute", "Unmute", "Play", "Pause", "Next track", "Previous song"
- 📸 **Utilities**: "Take a screenshot" (saves to Pictures), "Empty recycle bin", "What time is it", "What's today's date"
- 🔒 **System Power**: "Lock screen", "Sleep", "Shutdown" / "Restart" (safeguarded with a 20-second "confirm" check)
- ❌ **Closing Apps**: "Close Spotify", "Quit Chrome", "Kill Notepad"
- 🐙 **GitHub Integration**: "Open my top GitHub repo", "Open my GitHub profile" (configurable in Assistant Settings)
- 🔗 **Multi-Command Chaining**: "Open Chrome and open Spotify", "Take a screenshot and open Pictures"

### 🎀 Daisy's Cute Voices
Right-click Daisy and open **"Daisy's Voice 🎀"** to choose between cute girl voice personas:
- 🌸 **Ana (Super Cute & Playful - Default)** — high-spirited, sweet anime/pet voice
- 🎀 **Jenny (Warm & Cheerful)** — bubbly, warm, friendly
- ✨ **Emma (Sweet & Bubbly)** — gentle, perky, sweet
- 🌷 **Maisie (Cute British)** — cheerful British accent
- 💖 **Ava (Soft & Gentle)** — expressive, soft, affectionate
- 🔊 **Test Current Voice** — plays a cute greeting in Daisy's selected voice

## How it works

- `pet_widget.py` — the transparent always-on-top window and her
  animations (idle breathing, walking/running with directional turning,
  jumping/falling arcs, and resting/sitting) loaded directly from sprite
  sheets in the `Animations/` folder. Includes pixel-perfect rendering,
  speech bubble, and ground shadow.
- `voice.py` — handles microphone voice recognition, command parsing,
  and expressive neural cute girl voice speech synthesis (`edge-tts` with pitch/rate tuning and offline `pyttsx3` female fallback).
- `brain.py` — sends questions to OpenAI's API (`gpt-4o-mini`, etc.), Gemini's API, or Groq's API, with auto-detection based on key format and multi-model fallback, returning her answer as plain text.
- `main.py` — ties it together: system tray (with matching sprite icon),
  voice listener worker, right-click menu with voice selector, and background threads.

## Extending Daisy

Ideas for next steps, roughly in order of effort:

1. **More states** — add "sleep" (after N minutes idle), "eat" (drag a
   file onto her), "wave" on startup.
2. **Global hotkey** — bind a key combo (e.g. via the `keyboard` package)
   to summon her or open the ask dialog without right-clicking.
3. **Voice** — add text-to-speech (`pyttsx3`, fully offline and free) so
   she speaks her answers instead of only showing them.
4. **Real sprite art** — replace the procedural drawing with a sprite
   sheet (free ones are available on itch.io / OpenGameArt) for smoother,
   more expressive animation.
5. **Memory** — keep a short conversation history so follow-up questions
   have context, instead of treating every question independently.

## Notes on Models and Environment Variables

- **Google Gemini**: Free tier, no credit card. Customize model with `DAISY_GEMINI_MODEL`. Some free-tier
  projects can hit a Google-side access review (403 "project denied access") unrelated to anything in your
  setup — if that happens, Groq is a solid free fallback.
- **Groq**: Free tier, no credit card, no billing setup. Defaults to `openai/gpt-oss-20b` (lightning fast). Customize
  model with `DAISY_GROQ_MODEL` (e.g. `openai/gpt-oss-120b` or `qwen/qwen3.6-27b`).
- **OpenAI**: Supports `gpt-4o-mini` by default (fast & low-cost). Customize model with `DAISY_OPENAI_MODEL`
  (e.g. `gpt-4o`). Requires a payment method on file in your OpenAI account billing settings.
- **Provider Override**: If you want to force a specific provider, set `DAISY_PROVIDER=openai`,
  `DAISY_PROVIDER=gemini`, or `DAISY_PROVIDER=groq`.
