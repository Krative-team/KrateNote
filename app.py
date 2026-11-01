import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "KrateNote Whisper Online", "auto_lang": True})

@app.route("/transcribe", methods=["POST", "OPTIONS"])
def transcribe():
    if request.method == "OPTIONS":
        return "", 200
    
    if 'file' not in request.files:
        return jsonify({"error": "No file"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty file"}), 400

    try:
        # AUTO LANGUAGE DETECTION - No language parameter!
        # Groq Whisper will auto-detect Ibibio, Efik, Hausa, Yoruba, English, etc.
        transcription = client.audio.transcriptions.create(
            file=(file.filename, file.read()),
            model="whisper-large-v3",
            response_format="verbose_json",  # This returns language detected
            temperature=0.0
        )
        
        # verbose_json returns object with text and language
        text = transcription.text if hasattr(transcription, 'text') else str(transcription)
        detected_lang = transcription.language if hasattr(transcription, 'language') else "en"
        duration = transcription.duration if hasattr(transcription, 'duration') else 0

        print(f"Detected: {detected_lang} -> {text[:100]}")

        return jsonify({
            "text": text,
            "language": detected_lang,  # e.g. 'en', 'ha', 'yo', 'fr', 'es'
            "duration": duration
        })

    except Exception as e:
        print(f"Error: {e}")
        # Fallback - try without verbose_json
        try:
            file.stream.seek(0)
            transcription = client.audio.transcriptions.create(
                file=(file.filename, file.read()),
                model="whisper-large-v3",
                temperature=0.0
            )
            text = transcription.text if hasattr(transcription, 'text') else str(transcription)
            return jsonify({"text": text, "language": "auto"})
        except Exception as e2:
            return jsonify({"error": str(e2)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
