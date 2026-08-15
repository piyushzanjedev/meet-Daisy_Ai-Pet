"""
brain.py
Daisy's "high knowledge" brain, powered by Google's Gemini API, OpenAI API,
or Groq API (free, no credit card required).

Get an API key at:
    Google Gemini (Free): https://aistudio.google.com/apikey
    Groq (Free):          https://console.groq.com/keys
    OpenAI:                https://platform.openai.com/api-keys

Then set it as an environment variable or configure it directly in Daisy:
    Windows (persist):  setx GEMINI_API_KEY "your-key-here"
                        setx GROQ_API_KEY "your-key-here"
                        setx OPENAI_API_KEY "your-key-here"
    macOS/Linux:        export GEMINI_API_KEY="your-key-here"
                        export GROQ_API_KEY="your-key-here"
                        export OPENAI_API_KEY="your-key-here"
"""

import os
from typing import Optional, List, Tuple
import requests

# Supported Gemini models in priority order
CANDIDATE_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-pro-latest",
]

# Supported OpenAI models in priority order
CANDIDATE_OPENAI_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-3.5-turbo",
]

# Supported Groq models in priority order (free tier, no credit card required)
CANDIDATE_GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
]

SYSTEM_PROMPT = (
    "You are Daisy, an adorable, cheerful, and sweet desktop pet that lives on the "
    "user's screen. Answer the user's question in 2-3 short, friendly, and cute sentences. "
    "Maintain a charming, enthusiastic, and lovable pet personality. Do not use markdown formatting, asterisks, or bullet "
    "points, since your reply is spoken aloud and shown in a small speech bubble."
)


class BrainError(Exception):
    """Raised when Daisy can't get an answer (missing key, network, access denied, etc.)."""


def detect_provider(key: Optional[str]) -> str:
    """Detects whether an API key belongs to OpenAI, Google Gemini, or Groq."""
    forced_provider = os.environ.get("DAISY_PROVIDER", "").strip().lower()
    if forced_provider in ("openai", "gemini", "groq"):
        return forced_provider

    if key:
        clean_key = key.strip()
        if clean_key.startswith("gsk_"):
            return "groq"
        if clean_key.startswith("sk-"):
            return "openai"
    return "gemini"


def get_key_file_path() -> str:
    """Returns the path to the local persisted API key file."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    primary = os.path.join(base_dir, ".api_key")
    if os.path.exists(primary):
        return primary
    gemini_fallback = os.path.join(base_dir, ".gemini_key")
    if os.path.exists(gemini_fallback):
        return gemini_fallback
    return primary


def load_api_key() -> Optional[str]:
    """Loads API key, preferring the locally saved key file over environment
    variables. The file reflects the user's most recent explicit choice made
    via Daisy's 'Set API Key' menu, so it should win over an environment
    variable that may be a stale leftover from earlier setup/testing (e.g. a
    'setx OPENAI_API_KEY ...' run once and forgotten, which would otherwise
    silently shadow a newer, correct key saved through the UI)."""
    # Check key files (.api_key or .gemini_key) first
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for filename in (".api_key", ".gemini_key"):
        path = os.path.join(base_dir, filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        provider = detect_provider(content)
                        if provider == "openai":
                            os.environ["OPENAI_API_KEY"] = content
                        elif provider == "groq":
                            os.environ["GROQ_API_KEY"] = content
                        else:
                            os.environ["GEMINI_API_KEY"] = content
                        os.environ["DAISY_API_KEY"] = content
                        return content
            except Exception:
                pass

    # Fall back to environment variables only if no saved file exists
    for env_var in ("DAISY_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"):
        key = os.environ.get(env_var)
        if key and key.strip():
            return key.strip()

    return None


def save_api_key(key: str) -> str:
    """Saves API key locally and updates current process environment.

    Returns the path the key was written to. Raises BrainError if the
    write fails, instead of silently discarding the key (a key that only
    lives in os.environ disappears the moment the process exits, which is
    why "saved" keys can appear to vanish after quitting Daisy)."""
    key = key.strip()
    provider = detect_provider(key)
    os.environ["DAISY_API_KEY"] = key
    if provider == "openai":
        os.environ["OPENAI_API_KEY"] = key
    elif provider == "groq":
        os.environ["GROQ_API_KEY"] = key
    else:
        os.environ["GEMINI_API_KEY"] = key

    base_dir = os.path.dirname(os.path.abspath(__file__))
    key_file = os.path.join(base_dir, ".api_key")
    try:
        with open(key_file, "w", encoding="utf-8") as f:
            f.write(key)
        # Confirm what actually landed on disk, not just that write() didn't throw.
        with open(key_file, "r", encoding="utf-8") as f:
            written = f.read().strip()
        if written != key:
            raise IOError(f"File content mismatch after write to {key_file}")
    except Exception as exc:
        raise BrainError(
            f"Key kept for this session only \u2014 it was NOT saved to disk at "
            f"{key_file} ({exc}). It will be lost when Daisy closes. Check that "
            f"this folder isn't read-only, isn't inside a permission-restricted "
            f"location, and isn't blocked by antivirus/OneDrive."
        ) from exc

    return key_file


def get_key_status() -> Tuple[Optional[str], str]:
    """Returns (masked_key, provider_name) for display in settings UI."""
    key = load_api_key()
    if not key:
        return None, "None"
    provider = detect_provider(key)
    provider_name = {"openai": "OpenAI", "groq": "Groq"}.get(provider, "Gemini")
    masked = (key[:6] + "..." + key[-4:]) if len(key) > 10 else "***"
    return masked, provider_name


def _ask_gemini(question: str, key: str, timeout: int = 20) -> str:
    """Send question to Google Gemini REST API."""
    custom_model = os.environ.get("DAISY_GEMINI_MODEL")
    models_to_try: List[str] = [custom_model] if custom_model else list(CANDIDATE_GEMINI_MODELS)

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{SYSTEM_PROMPT}\n\nQuestion: {question}"}],
            }
        ]
    }

    last_error: Optional[str] = None
    status_code: int = 0

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            resp = requests.post(
                url,
                params={"key": key},
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise BrainError(f"Network error: {exc}") from exc

        status_code = resp.status_code

        if status_code == 200:
            data = resp.json()
            try:
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                clean_text = text.replace("*", "").replace("#", "").strip()
                return clean_text
            except (KeyError, IndexError, TypeError):
                raise BrainError("Unexpected response format from Gemini.")

        try:
            err_data = resp.json()
            err_msg = err_data.get("error", {}).get("message", resp.text[:150])
        except Exception:
            err_msg = resp.text[:150]

        last_error = err_msg

        if status_code == 404:
            continue

        if status_code == 401:
            raise BrainError(
                "Invalid Gemini API key (401). Please check and copy your key from https://aistudio.google.com/apikey"
            )

        if status_code == 403:
            raise BrainError(
                "Gemini API Error (403): Project access denied. Please generate a fresh key at https://aistudio.google.com/apikey"
            )

        if status_code == 429:
            raise BrainError(
                "Gemini API Quota Exceeded (429). Please check your quota on Google AI Studio."
            )

    raise BrainError(f"Gemini API Error ({status_code}): {last_error or 'Unable to contact Gemini.'}")


def _ask_openai(question: str, key: str, timeout: int = 20) -> str:
    """Send question to OpenAI Chat Completions REST API."""
    custom_model = os.environ.get("DAISY_OPENAI_MODEL")
    models_to_try: List[str] = [custom_model] if custom_model else list(CANDIDATE_OPENAI_MODELS)

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    last_error: Optional[str] = None
    status_code: int = 0

    for model in models_to_try:
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            "max_tokens": 150,
            "temperature": 0.7,
        }

        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise BrainError(f"Network error: {exc}") from exc

        status_code = resp.status_code

        if status_code == 200:
            data = resp.json()
            try:
                text = data["choices"][0]["message"]["content"].strip()
                clean_text = text.replace("*", "").replace("#", "").strip()
                return clean_text
            except (KeyError, IndexError, TypeError):
                raise BrainError("Unexpected response format from OpenAI.")

        try:
            err_data = resp.json()
            err_msg = err_data.get("error", {}).get("message", resp.text[:150])
        except Exception:
            err_msg = resp.text[:150]

        last_error = err_msg

        if status_code == 404:
            continue

        if status_code == 401:
            raise BrainError(
                "Invalid OpenAI API key (401). Please check your key at https://platform.openai.com/api-keys"
            )

        if status_code == 429:
            raise BrainError(
                "OpenAI API Quota / Rate limit exceeded (429). Please check your OpenAI billing / usage limits at https://platform.openai.com/account/billing"
            )

    raise BrainError(f"OpenAI API Error ({status_code}): {last_error or 'Unable to contact OpenAI.'}")


def _ask_groq(question: str, key: str, timeout: int = 20) -> str:
    """Send question to Groq's OpenAI-compatible Chat Completions REST API."""
    custom_model = os.environ.get("DAISY_GROQ_MODEL")
    models_to_try: List[str] = [custom_model] if custom_model else list(CANDIDATE_GROQ_MODELS)

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    last_error: Optional[str] = None
    status_code: int = 0

    for model in models_to_try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            "max_tokens": 150,
            "temperature": 0.7,
        }

        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise BrainError(f"Network error: {exc}") from exc

        status_code = resp.status_code

        if status_code == 200:
            data = resp.json()
            try:
                text = data["choices"][0]["message"]["content"].strip()
                clean_text = text.replace("*", "").replace("#", "").strip()
                return clean_text
            except (KeyError, IndexError, TypeError):
                raise BrainError("Unexpected response format from Groq.")

        try:
            err_data = resp.json()
            err_msg = err_data.get("error", {}).get("message", resp.text[:150])
        except Exception:
            err_msg = resp.text[:150]

        last_error = err_msg

        if status_code == 404:
            continue

        if status_code == 401:
            raise BrainError(
                "Invalid Groq API key (401). Please check your key at https://console.groq.com/keys"
            )

        if status_code == 429:
            raise BrainError(
                "Groq API Rate limit exceeded (429). The free tier resets daily; try again shortly."
            )

    raise BrainError(f"Groq API Error ({status_code}): {last_error or 'Unable to contact Groq.'}")


def ask(question: str, api_key: Optional[str] = None, timeout: int = 20) -> str:
    """Send a question to Gemini or OpenAI and return Daisy's reply as plain text."""
    key = api_key or load_api_key()
    if not key:
        raise BrainError(
            "No API key found. Right-click Daisy -> 'Set API Key...' to configure your OpenAI, Gemini, or Groq key."
        )

    provider = detect_provider(key)
    if provider == "openai":
        return _ask_openai(question, key, timeout=timeout)
    elif provider == "groq":
        return _ask_groq(question, key, timeout=timeout)
    else:
        return _ask_gemini(question, key, timeout=timeout)
