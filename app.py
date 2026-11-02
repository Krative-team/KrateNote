import os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
client = None
if GROQ_KEY:
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_KEY)
        print(f"Groq client ready, key len {len(GROQ_KEY)}")
    except Exception as e:
        print(f"Groq init error: {e}")
        import traceback
        traceback.print_exc()

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "KrateNote Online",
        "groq_ready": client is not None,
        "key_exists": bool(GROQ_KEY),
        "key_len": len(GROQ_KEY),
        "translate": True
    })

@app.route("/transcribe", methods=["POST", "OPTIONS"])
def transcribe():
    if request.method == "OPTIONS":
        return "", 200
    if not client:
        return jsonify({"error": "Groq client not ready"}), 500
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
        return jsonify({"text": transcription.text, "language": getattr(transcription, 'language', 'en')})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/translate", methods=["POST", "OPTIONS"])
def translate():
    if request.method == "OPTIONS":
        return "", 200
    if not client:
        return jsonify({"error": "Groq not ready"}), 500
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    to_code = data.get("to", "en")
    if not text:
        return jsonify({"error": "No text"}), 400
    
    names = {"ibb":"Ibibio from Akwa Ibom Nigeria","efi":"Efik from Cross River Nigeria","pcm":"Nigerian Pidgin English","ha":"Hausa","yo":"Yoruba","ig":"Igbo","en":"English","fr":"French","es":"Spanish"}
    target = names.get(to_code, to_code)
    
    try:
        comp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role":"system","content":f"Translate to {target}. Only return translation."},
                {"role":"user","content":text}
            ],
            temperature=0.2, max_tokens=800
        )
        return jsonify({"translated": comp.choices[0].message.content.strip(), "to": to_code})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
