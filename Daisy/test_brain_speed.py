import time
import brain

t0 = time.time()
try:
    ans = brain.ask("Hello, who are you?")
    t1 = time.time()
    print("Answer:", ans)
    print(f"Time taken: {(t1-t0)*1000:.1f}ms")
except Exception as e:
    print("Error:", e)
