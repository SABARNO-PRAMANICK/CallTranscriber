#I'm working on this

import os
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from groq import Groq

app = FastAPI()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)
MODEL = "playai-tts"
VOICE = "Fritz-PlayAI"  # Choose from Groq/PlayAI voices

@app.post("/")
async def webhook_handler(request: Request):
    body = await request.body()
    text = body.decode("utf-8")

    def stream_audio():
        response = client.audio.speech.create(
            model=MODEL,
            voice=VOICE,
            input=text,
            response_format="wav",
            stream=True  # Streaming is crucial for real-time output
        )
        for chunk in response.iter_content(chunk_size=4096):
            yield chunk

    return StreamingResponse(stream_audio(), media_type="audio/wav")
