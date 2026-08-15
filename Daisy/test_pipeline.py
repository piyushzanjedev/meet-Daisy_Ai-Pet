import time
import asyncio
import io
import re
import soundfile as sf
import sounddevice as sd
import edge_tts

def split_into_sentences(text: str):
    # Split text into sentences by punctuation (. ! ? \n)
    sentences = re.split(r'(?<=[.!?\n])\s+', text.strip())
    # Filter empty or whitespace-only
    return [s.strip() for s in sentences if s.strip()]

async def synthesize_sentence(sentence: str, voice_id="en-US-AnaNeural", pitch="+6Hz", rate="+4%"):
    comm = edge_tts.Communicate(sentence, voice_id, pitch=pitch, rate=rate)
    bio = io.BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            bio.write(chunk["data"])
    bio.seek(0)
    data, fs = sf.read(bio)
    return data, fs

async def test_pipelined():
    text = "Hello! I am Daisy the desktop pet. I love running around your screen and helping you with everything!"
    sentences = split_into_sentences(text)
    print("Sentences:", sentences)
    
    t0 = time.time()
    # Start task for sentence 0
    first_data, fs = await synthesize_sentence(sentences[0])
    t_first = time.time()
    print(f"Time until first sentence ready to play: {(t_first - t0)*1000:.1f}ms")

if __name__ == "__main__":
    asyncio.run(test_pipelined())
