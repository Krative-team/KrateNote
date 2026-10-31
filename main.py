from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import os
import requests
import tempfile

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("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")

@app.get("/")
def home():
    return {"status": "KrateNote Whisper API online - Groq"}

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    # Keep original extension (m4a for iPhone, webm for Android)
    original_ext = os.path.splitext(file.filename)[1] or ".webm"
    if not original_ext:
        # Detect from content_type
        if "mp4" in (file.content_type or ""):
            original_ext = ".m4a"
        else:
            original_ext = ".webm"
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=original_ext) as tmp:
        content = await file.read()
        print(f"Received: {file.filename}, type: {file.content_type}, size: {len(content)} bytes, saving as {original_ext}")
        tmp.write(content)
        path = tmp.name

    try:
        with open(path, "rb") as f:
            # CRITICAL FIX: Send filename tuple
            res = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": (f"audio{original_ext}", f, file.content_type or "audio/webm")},
                data={"model": "whisper-large-v3"}
            )
        print(f"Groq status: {res.status_code}")
        print(f"Groq response: {res.text[:500]}")
        
        if res.status_code != 200:
            return {"error": f"Groq error {res.status_code}: {res.text}", "text": ""}
        
        data = res.json()
        text = data.get("text", "")
        print(f"Transcribed: {text}")
        return {"text": text}
    except Exception as e:
        print(f"Exception: {e}")
        return {"error": str(e), "text": ""}
    finally:
        if os.path.exists(path):
            os.remove(path)
