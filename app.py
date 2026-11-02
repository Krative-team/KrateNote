import os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

print("=== DEBUG START ===")
print(f"All env keys: {list(os.environ.keys())}")
GROQ_KEY = os.environ.get("GROQ_API_KEY")
print(f"GROQ_API_KEY exists: {GROQ_KEY is not None}")
if GROQ_KEY:
    print(f"GROQ_KEY length: {len(GROQ_KEY)}")
    print(f"GROQ_KEY starts with: {GROQ_KEY[:8]}...")
else:
    print("GROQ_API_KEY IS NONE - NOT SET IN RENDER!")

client = None
if GROQ_KEY:
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_KEY)
        print("Groq client ready - SUCCESS")
    except Exception as e:
        print(f"Groq init error: {e}")
        import traceback
        traceback.print_exc()
else:
    print("WARNING: GROQ_API_KEY not set!")
print("=== DEBUG END ===")

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "KrateNote Online",
        "groq_ready": client is not None,
        "key_exists": GROQ_KEY is not None,
        "key_len": len(GROQ_KEY) if GROQ_KEY else 0,
        "env_keys_count": len(os.environ),
        "translate": True
    })

@app.route("/transcribe", methods=["POST", "OPTIONS"])
def transcribe():
    if request.method == "OPTIONS":
        return "", 200
    if not client:
        return jsonify({"error": "Server not configured: GROQ_API_KEY missing", "key_exists": GROQ_KEY is not None}), 500
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
        })
    except Exception as e:
        print(f"Transcribe error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/translate", methods=["POST", "OPTIONS"])
def translate():
    if request.method == "OPTIONS":
        return "", 200
    if not client:
        return jsonify({"error": "GROQ_API_KEY missing", "key_exists": GROQ_KEY is not None}), 500
    data = request.get_json()
    text = data.get("text", "").strip()
    to_code = data.get("to", "en")
    if not text:
        return jsonify({"error": "No text"}), 400
    lang_map = {
        "en": "English", "ibb": "Ibibio language from Akwa Ibom Nigeria", "efi": "Efik language from Cross River Nigeria",
        "pcm": "Nigerian Pidgin English", "ha": "Hausa", "yo": "Yoruba", "ig": "Igbo",
        "fr": "French", "es": "Spanish", "de": "German", "pt": "Portuguese"
    }
    target_name = lang_map.get(to_code, to_code)
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": f"Translate to {target_name}. Only output translation."},
                {"role": "user", "content": text}
            ],
            temperature=0.2, max_tokens=1000
        )
        translated = completion.choices[0].message.content.strip()
        return jsonify({"translated": translated, "to": to_code})
    except Exception as e:
        print(f"Translate error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
