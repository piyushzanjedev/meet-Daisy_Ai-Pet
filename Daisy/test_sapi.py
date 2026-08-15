import time
import pyttsx3

t0 = time.time()
engine = pyttsx3.init()
t1 = time.time()
print(f"pyttsx3 init: {(t1-t0)*1000:.1f}ms")

voices = engine.getProperty("voices")
for v in voices:
    print("Voice:", v.name, v.id)

t2 = time.time()
engine.say("Hello")
engine.runAndWait()
t3 = time.time()
print(f"pyttsx3 speak 'Hello': {(t3-t2)*1000:.1f}ms")
