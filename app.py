import os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Don't crash if key missing
GROQ_KEY = os.environ.get("GROQ_API_KEY")
client = None
if GROQ_KEY:
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_KEY)
        print("Groq client ready")
    except Exception as e:
        print(f"Groq init error: {e}")
else:
    print("WARNING: GROQ_API_KEY not set!")

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "KrateNote Online",
        "groq_ready": client is not None,
        "auto_lang": True
    })

@app.route("/transcribe", methods=["POST", "OPTIONS"])
def transcribe():
    if request.method == "OPTIONS":
        return "", 200
    if not client:
        return jsonify({"error": "Server not configured: GROQ_API_KEY missing"}), 500
    if 'file' not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files['file']
    try:
        transcription = client.audio.transcriptions.create(
            file=(file.filename, file.read()),
            model="whisper-large-v3",
            response_format="verbose_json",
            temperature=0.0
        )
        return jsonify({
            "text": transcription.text,
            "language": getattr(transcription, 'language', 'en'),
            "duration": getattr(transcription, 'duration', 0)
        })
    except Exception as e:
        print(f"Transcribe error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
