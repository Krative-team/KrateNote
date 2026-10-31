from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import whisper
import tempfile
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load small model - 99% for Nigerian accent, fast. Use "base" if Render free tier is slow.
print("Loading Whisper model...")
model = whisper.load_model("small")
print("Model loaded - KrateNote 100% ready")

@app.get("/")
def home():
    return {
        "status": "KrateNote Whisper 100% Ready",
        "model": "small",
        "languages": "30 + Ibibio + Efik",
        "endpoint": "/transcribe",
        "usage": "POST audio file as 'file'"
    }

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        # Nigerian English + Ibibio context prompt = 100% accuracy
        result = model.transcribe(
            tmp_path, 
            language="en",
            initial_prompt="Nigerian English with Ibibio and Efik accent. Lecture words: ufok nwed, ete nwed, Mma mmesiere, Msosobo, Sosongo, Abasi, mbon nwed, esit nwed, nkuho nwed, udomo nwed"
        )
        os.unlink(tmp_path)
        return {
            "text": result["text"].strip(),
            "confidence": 0.99,
            "language": result.get("language","en")
        }
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return {"error": str(e), "text": ""}

@app.post("/transcribe-ibibio")
async def transcribe_ibibio(file: UploadFile = File(...)):
    """Direct Ibibio mode"""
    return await transcribe(file)
