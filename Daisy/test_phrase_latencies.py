import time
import io
import asyncio
import soundfile as sf
import sounddevice as sd
import edge_tts

async def measure_edge_tts(phrase):
    t0 = time.time()
    comm = edge_tts.Communicate(phrase, "en-US-AnaNeural", pitch="+6Hz", rate="+4%")
    bio = io.BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            bio.write(chunk["data"])
    t_downloaded = time.time()
    bio.seek(0)
    data, fs = sf.read(bio)
    t_decoded = time.time()
    print(f"Phrase: '{phrase}'")
    print(f"  Download time: {(t_downloaded - t0)*1000:.1f}ms")
    print(f"  Decode time: {(t_decoded - t_downloaded)*1000:.1f}ms")
    print(f"  Total time before audio output: {(t_decoded - t0)*1000:.1f}ms")
    print(f"  Audio duration: {len(data)/fs:.2f}s")

if __name__ == "__main__":
    asyncio.run(measure_edge_tts("Running fast!"))
    asyncio.run(measure_edge_tts("Walking!"))
    asyncio.run(measure_edge_tts("Daisy is an adorable desktop pet that lives on your screen."))
