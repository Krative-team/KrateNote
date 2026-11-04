import os
import json
import hashlib
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
SECRET = os.environ.get("SECRET_KEY", "kratenote-secret-2025-super")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

client = None
if GROQ_KEY:
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_KEY)
        print(f"Groq client ready, key len {len(GROQ_KEY)}")
    except Exception as e:
        print(f"Groq init error: {e}")

# ===== NEON POSTGRES - REPLACES users.json =====
db = None
if DATABASE_URL:
    try:
        import psycopg2
        import psycopg2.extras
        db = psycopg2.connect(DATABASE_URL, sslmode='require')
        db.autocommit = True
        with db.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    email TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    pw TEXT NOT NULL,
                    created TEXT NOT NULL
                )
            """)
        print("Neon connected - users table ready")
    except Exception as e:
        print(f"Neon failed: {e}")
        db = None
else:
    print("WARNING: No DATABASE_URL set!")

def load_users():
    if db:
        try:
            with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT email, name, pw, created FROM users")
                rows = cur.fetchall()
                return {r['email']: {"name": r['name'], "email": r['email'], "pw": r['pw'], "created": r['created']} for r in rows}
        except Exception as e:
            print(f"DB load error: {e}")
    return {}

def save_user(email, name, pw_hash):
    if db:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, name, pw, created) VALUES (%s,%s,%s,%s) ON CONFLICT (email) DO NOTHING",
                (email, name, pw_hash, datetime.now().isoformat())
            )
        return True
    return False

def delete_user(email):
    if not db:
        return False
    try:
        with db.cursor() as cur:
            cur.execute("DELETE FROM users WHERE email = %s", (email,))
            return cur.rowcount > 0
    except Exception as e:
        print(f"DB delete error: {e}")
        return False

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "KrateNote Online V9 - Neon",
        "groq_ready": client is not None,
        "key_exists": bool(GROQ_KEY),
        "key_len": len(GROQ_KEY),
        "translate": True,
        "auth": True,
        "model": "openai/gpt-oss-20b + dictionary",
        "db": "neon-postgres" if db else "NOT CONNECTED - CHECK DATABASE_URL",
        "users_count": len(load_users())
    })

@app.route("/register", methods=["POST", "OPTIONS"])
def register():
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json() or {}
    email = data.get("email","").lower().strip()
    name = data.get("name","").strip()
    password = data.get("password","")
    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400
    if not name:
        return jsonify({"error": "Name required"}), 400
    if not password or len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    users = load_users()
    if email in users:
        return jsonify({"error": "Email already registered. Please login"}), 400
    save_user(email, name, hash_pw(password))
    print(f"New user registered: {email}")
    return jsonify({"message": "Account created! Please login", "email": email})

@app.route("/login", methods=["POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json() or {}
    email = data.get("email","").lower().strip()
    password = data.get("password","")
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    users = load_users()
    if email not in users:
        return jsonify({"error": "Account not found. Please register"}), 401
    if users[email]["pw"] != hash_pw(password):
        return jsonify({"error": "Invalid password"}), 401
    try:
        import jwt
        payload = {"email": email, "name": users[email]["name"], "exp": datetime.utcnow() + timedelta(days=7)}
        token = jwt.encode(payload, SECRET, algorithm="HS256")
    except ImportError:
        token = hashlib.sha256(f"{email}{SECRET}{datetime.now()}".encode()).hexdigest()
    print(f"User login: {email}")
    return jsonify({"token": token, "name": users[email]["name"], "email": email, "message": "Login successful"})

@app.route("/me", methods=["GET", "OPTIONS"])
def me():
    if request.method == "OPTIONS":
        return "", 200
    auth = request.headers.get("Authorization","")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "No token"}), 401
    token = auth.replace("Bearer ","")
    try:
        import jwt
        decoded = jwt.decode(token, SECRET, algorithms=["HS256"])
        return jsonify({"email": decoded["email"], "name": decoded.get("name","User")})
    except Exception as e:
        return jsonify({"error": "Invalid token", "details": str(e)}), 401

# ===== DELETE ACCOUNT - TRUE DELETE FROM NEON =====
@app.route("/delete-account", methods=["DELETE", "OPTIONS"])
def delete_account():
    if request.method == "OPTIONS":
        return "", 200
    # 1. Must have token
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "No token"}), 401
    token = auth.replace("Bearer ", "")

    # 2. Verify token - person fit only delete their own account
    try:
        import jwt
        decoded = jwt.decode(token, SECRET, algorithms=["HS256"])
        token_email = decoded.get("email", "").lower().strip()
    except Exception as e:
        return jsonify({"error": "Invalid or expired token", "details": str(e)}), 401

    data = request.get_json(silent=True) or {}
    req_email = data.get("email", "").lower().strip() or token_email

    # 3. No allow person delete another person account
    if req_email != token_email:
        return jsonify({"error": "You can only delete your own account"}), 403

    if not db:
        return jsonify({"error": "Database not connected"}), 500

    # 4. Delete from Neon
    deleted = delete_user(req_email)
    if not deleted:
        # Check if user still dey - if no, e don already delete
        users = load_users()
        if req_email not in users:
            return jsonify({"message": "Account already deleted", "email": req_email, "deleted": True})
        return jsonify({"error": "Could not delete account"}), 500

    print(f"User deleted account: {req_email}")
    return jsonify({"message": "Account deleted successfully", "email": req_email, "deleted": True})

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
        print(f"Transcribe error: {e}")
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
        system_prompt = """You are an expert Ibibio translator from Akwa Ibom State, Nigeria. You MUST translate to Ibibio, not English. Ibibio vocabulary - USE THESE WORDS: Hello = Mmesiere, Students = Nditɔ̃ / Nditɔ, How are you? = Nte idem fo? / Sosongo idem?, How are you all doing? = Nte idem mfo?, I hope = Mmenyeneke, You are good = Afo esongo / Afo asongo, Welcome = Eka abo / Sosongo, Today = Mfin, Today's class = Ufok nwed mfin, Class = Ufok nwed, Let's = Yak, Make it = Ya nam, Lively = Idara / Ufok idara, Lovely = Nnanga / Usung. Only return translation, no explanation."""
    elif to_code == "efi":
        system_prompt = """You are an expert Efik translator from Cross River State, Nigeria. Translate to Efik language. Efik vocabulary: Hello = Emem / Mesiere, Students = Nditɔ, How are you = Kam idem fo?, How are you all doing = Kam idem mfo?, Welcome = Sosongho / Ekaabo, Today = Mfin, Class = Ufok nwed. Only return translation."""
    elif to_code == "pcm":
        system_prompt = "You are a Nigerian Pidgin translator. Translate to Nigerian Pidgin. Use Una, Dey, How una dey, Wetin, Na, For, etc. Only return translation."
    else:
        names = {"en":"English","ha":"Hausa","yo":"Yoruba","ig":"Igbo","fr":"French","es":"Spanish","de":"German","pt":"Portuguese","it":"Italian","nl":"Dutch","ar":"Arabic","zh":"Chinese","ja":"Japanese","ko":"Korean","ru":"Russian","hi":"Hindi","sw":"Swahili","zu":"Zulu","am":"Amharic","tr":"Turkish","el":"Greek","he":"Hebrew","sv":"Swedish","no":"Norwegian","pl":"Polish","id":"Indonesian","th":"Thai"}
        target = names.get(to_code, to_code)
        system_prompt = f"You are a professional translator. Translate to {target}. Only return translation, no explanation."
    try:
        comp = client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role":"system","content": system_prompt},{"role":"user","content": text}], temperature=0.7, max_tokens=1200)
        translated = comp.choices[0].message.content.strip()
        if to_code in ["ibb","efi"] and ("cannot" in translated.lower() or "sorry" in translated.lower() or len(translated) < 5):
            comp = client.chat.completions.create(model="openai/gpt-oss-120b", messages=[{"role":"system","content": system_prompt},{"role":"user","content": text}], temperature=0.8, max_tokens=1200)
            translated = comp.choices[0].message.content.strip()
        return jsonify({"translated": translated, "to": to_code})
    except Exception as e:
        print(f"Translate error: {e}")
        try:
            comp = client.chat.completions.create(model="openai/gpt-oss-120b", messages=[{"role":"system","content": system_prompt},{"role":"user","content": text}], temperature=0.7, max_tokens=1200)
            return jsonify({"translated": comp.choices[0].message.content.strip(), "to": to_code})
        except Exception as e2:
            return jsonify({"error": str(e2)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
