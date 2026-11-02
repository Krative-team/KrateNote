import os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

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
        "auto_lang": True,
        "translate": True
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

@app.route("/translate", methods=["POST", "OPTIONS"])
def translate():
    if request.method == "OPTIONS":
        return "", 200
    if not client:
        return jsonify({"error": "GROQ_API_KEY missing"}), 500
    data = request.get_json()
    text = data.get("text", "").strip()
    to_code = data.get("to", "en")
    if not text:
        return jsonify({"error": "No text"}), 400

    lang_map = {
        "en": "English",
        "ibb": "Ibibio - a Nigerian language spoken in Akwa Ibom State. Translate naturally as Ibibio people speak",
        "efi": "Efik - a Nigerian language spoken in Cross River State, similar to Ibibio",
        "pcm": "Nigerian Pidgin English - informal West African English like 'How you dey?' 'Wetin happen?'",
        "ha": "Hausa", "yo": "Yoruba", "ig": "Igbo",
        "fr": "French", "es": "Spanish", "de": "German", "pt": "Portuguese",
        "it": "Italian", "nl": "Dutch", "ar": "Arabic", "zh": "Chinese",
        "ja": "Japanese", "ko": "Korean", "ru": "Russian", "hi": "Hindi",
        "sw": "Swahili", "zu": "Zulu", "am": "Amharic", "tr": "Turkish",
        "el": "Greek", "he": "Hebrew", "sv": "Swedish", "no": "Norwegian",
        "pl": "Polish", "id": "Indonesian", "th": "Thai"
    }
    target_name = lang_map.get(to_code, to_code)

    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": f"You are a professional translator. Translate to {target_name}. Only output the translation, no explanation."},
                {"role": "user", "content": text}
            ],
            temperature=0.2,
            max_tokens=1000
        )
        translated = completion.choices[0].message.content.strip()
        return jsonify({"translated": translated, "to": to_code})
    except Exception as e:
        print(f"Translate error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
