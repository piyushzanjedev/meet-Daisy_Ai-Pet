import time
import io
import asyncio
import soundfile as sf
import sounddevice as sd
import edge_tts
import pyttsx3

def profile_tts(text="Hello! I am Daisy the desktop pet."):
    print(f"Profiling TTS for text: '{text}'")
    
    # 1. Edge-TTS
    t0 = time.time()
    comm = edge_tts.Communicate(text, "en-US-AnaNeural", pitch="+6Hz", rate="+4%")
    bio = io.BytesIO()
    t1 = time.time()
    
    async def get_audio():
        first_chunk_time = None
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                if first_chunk_time is None:
                    first_chunk_time = time.time()
                bio.write(chunk["data"])
        return first_chunk_time

    first_chunk_t = asyncio.run(get_audio())
    t2 = time.time()
    
    bio.seek(0)
    data, fs = sf.read(bio)
    t3 = time.time()
    
    print(f"Edge-TTS Communicate object setup: {(t1-t0)*1000:.1f}ms")
    print(f"Edge-TTS Time to first audio chunk: {(first_chunk_t-t1)*1000:.1f}ms" if first_chunk_t else "No chunk")
    print(f"Edge-TTS Total stream download: {(t2-t1)*1000:.1f}ms")
    print(f"Soundfile MP3 decode time: {(t3-t2)*1000:.1f}ms")
    print(f"Audio length (seconds): {len(data)/fs:.2f}s")
    
    # 2. Pyttsx3
    t4 = time.time()
    engine = pyttsx3.init()
    t5 = time.time()
    engine.setProperty("rate", 175)
    print(f"pyttsx3 init time: {(t5-t4)*1000:.1f}ms")

if __name__ == "__main__":
    profile_tts()
