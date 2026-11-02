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
        "translate": True,
        "model": "openai/gpt-oss-20b + dictionary"
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
    
    if to_code == "ibb":
        system_prompt = """You are an expert Ibibio translator from Akwa Ibom State, Nigeria.
You MUST translate to Ibibio, not English.

Ibibio vocabulary - USE THESE WORDS:
Hello = Mmesiere
Students = Nditɔ̃ / Nditɔ
How are you? = Nte idem fo? / Sosongo idem?
How are you all doing? = Nte idem mfo?
I hope = Mmenyeneke
You are good = Afo esongo / Afo asongo
Welcome = Eka abo / Sosongo
Today = Mfin
Today's class = Ufok nwed mfin
Class = Ufok nwed
Let's = Yak
Make it = Ya nam
Lively = Idara / Ufok idara
Lovely = Nnanga / Usung

Examples you must follow style:
EN: Hello students, how are you all doing? I hope you are good today.
IBB: Mmesiere nditɔ̃, nte idem mfo? Mmenyeneke mfin afo esongo.

EN: Welcome to today's class
IBB: Eka abo mfin ufok nwed

Translate this now to Ibibio, mix Ibibio and small English if needed, but try Ibibio first. Only return translation, no explanation."""
    
    elif to_code == "efi":
        system_prompt = """You are an expert Efik translator from Cross River State, Nigeria.
Translate to Efik language.

Efik vocabulary:
Hello = Emem / Mesiere
Students = Nditɔ
How are you = Kam idem fo?
How are you all doing = Kam idem mfo?
Welcome = Sosongho / Ekaabo
Today = Mfin
Class = Ufok nwed

Example:
EN: Hello students -> EFIK: Emem nditɔ

Translate to Efik. Only return translation."""
    
    elif to_code == "pcm":
        system_prompt = "You are a Nigerian Pidgin translator. Translate to Nigerian Pidgin. Use Una, Dey, How una dey, Wetin, Na, For, etc. Only return translation."
    else:
        names = {"en":"English","ha":"Hausa","yo":"Yoruba","ig":"Igbo","fr":"French","es":"Spanish","de":"German","pt":"Portuguese","it":"Italian","nl":"Dutch","ar":"Arabic","zh":"Chinese","ja":"Japanese","ko":"Korean","ru":"Russian","hi":"Hindi","sw":"Swahili","zu":"Zulu","am":"Amharic","tr":"Turkish","el":"Greek","he":"Hebrew","sv":"Swedish","no":"Norwegian","pl":"Polish","id":"Indonesian","th":"Thai"}
        target = names.get(to_code, to_code)
        system_prompt = f"You are a professional translator. Translate to {target}. Only return translation, no explanation."

    try:
        # First try with 20b
        comp = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role":"system","content": system_prompt},
                {"role":"user","content": text}
            ],
            temperature=0.7,
            max_tokens=1200
        )
        translated = comp.choices[0].message.content.strip()
        
        # If model says it can't translate Ibibio/Efik, try bigger model
        if to_code in ["ibb","efi"] and ("cannot" in translated.lower() or "sorry" in translated.lower() or len(translated) < 5):
            comp = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role":"system","content": system_prompt},
                    {"role":"user","content": text}
                ],
                temperature=0.8,
                max_tokens=1200
            )
            translated = comp.choices[0].message.content.strip()
            
        return jsonify({"translated": translated, "to": to_code})
    except Exception as e:
        print(f"Translate error: {e}")
        # Try fallback to 120b on error
        try:
            comp = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role":"system","content": system_prompt},{"role":"user","content": text}],
                temperature=0.7,
                max_tokens=1200
            )
            return jsonify({"translated": comp.choices[0].message.content.strip(), "to": to_code})
        except Exception as e2:
            return jsonify({"error": str(e2)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
