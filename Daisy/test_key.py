import brain

key = brain.load_api_key()
print("Loaded key:", key[:8] if key else "None")
provider = brain.detect_provider(key)
print("Provider:", provider)
