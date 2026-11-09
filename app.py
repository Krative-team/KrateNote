import os
import json
import hashlib
import secrets
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    email TEXT NOT NULL,
                    note_id TEXT NOT NULL,
                    title TEXT,
                    text TEXT,
                    date TEXT,
                    lang TEXT,
                    code TEXT,
                    flag TEXT,
                    folder TEXT,
                    subject TEXT,
                    pinned BOOLEAN DEFAULT FALSE,
                    archived BOOLEAN DEFAULT FALSE,
                    edited BOOLEAN DEFAULT FALSE,
                    edited_at BIGINT DEFAULT 0,
                    subs JSONB DEFAULT '[]'::jsonb,
                    highlights JSONB DEFAULT '[]'::jsonb,
                    ts BIGINT DEFAULT 0,
                    updated_at TEXT,
                    PRIMARY KEY (email, note_id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public_notes (
                    public_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    note_id TEXT NOT NULL,
                    title TEXT,
                    text TEXT,
                    folder TEXT,
                    subject TEXT,
                    date TEXT,
                    ts BIGINT DEFAULT 0,
                    created_at TEXT,
                    UNIQUE(email, note_id)
                )
            """)
            cur.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS archived BOOLEAN DEFAULT FALSE")
            cur.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS edited BOOLEAN DEFAULT FALSE")
            cur.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS edited_at BIGINT DEFAULT 0")
        print("Neon connected - users + notes + public_notes tables ready")
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

def delete_user_notes(email):
    if not db:
        return
    try:
        with db.cursor() as cur:
            cur.execute("DELETE FROM notes WHERE email = %s", (email,))
            cur.execute("DELETE FROM public_notes WHERE email = %s", (email,))
    except Exception as e:
        print(f"DB delete notes error: {e}")

def load_notes_for(email):
    if not db:
        return []
    try:
        with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT note_id, title, text, date, lang, code, flag, folder, subject, pinned, archived, edited, edited_at, subs, highlights, ts FROM notes WHERE email=%s ORDER BY ts DESC", (email,))
            rows = cur.fetchall()
            out=[]
            for r in rows:
                subs = r['subs']
                if isinstance(subs, str):
                    try: subs=json.loads(subs)
                    except: subs=[]
                hl = r['highlights']
                if isinstance(hl, str):
                    try: hl=json.loads(hl)
                    except: hl=[]
                raw_date = (r['date'] or "").replace(" (edited)", "").replace("(edited)", "").strip()
                is_edited = bool(r.get('edited', False) if isinstance(r, dict) else False)
                if "(edited)" in (r['date'] or ""):
                    is_edited = True
                edited_at = 0
                try:
                    edited_at = int(r.get('edited_at', 0) or 0) if isinstance(r, dict) else 0
                except:
                    edited_at = 0
                if is_edited and not edited_at:
                    edited_at = int(r['ts'] or 0)
                out.append({
                    "id": r['note_id'], "title": r['title'] or "", "text": r['text'] or "",
                    "date": raw_date, "lang": r['lang'] or "", "code": r['code'] or "",
                    "flag": r['flag'] or "🇬🇧", "folder": r['folder'] or "General",
                    "subject": r['subject'] or "General", "pinned": bool(r['pinned']),
                    "archived": bool(r.get('archived', False) if isinstance(r, dict) else False),
                    "edited": is_edited, "editedAt": edited_at,
                    "subs": subs or [], "highlights": hl or [], "ts": r['ts'] or 0
                })
            return out
    except Exception as e:
        print(f"DB load notes error: {e}")
        return []

def save_notes_for(email, notes_list):
    if not db:
        return False
    try:
        with db.cursor() as cur:
            cur.execute("DELETE FROM notes WHERE email=%s", (email,))
            for n in notes_list:
                clean_date = str(n.get("date","") or "").replace(" (edited)", "").replace("(edited)", "").strip()
                is_edited = bool(n.get("edited", False))
                if "(edited)" in str(n.get("date","") or ""):
                    is_edited = True
                edited_at = int(n.get("editedAt", 0) or n.get("edited_at", 0) or 0)
                if is_edited and not edited_at:
                    edited_at = int(n.get("ts", 0) or 0)
                note_id_val = str(n.get("id") or n.get("note_id") or hashlib.sha256(f"{email}{n.get('title','')}{n.get('ts',0)}".encode()).hexdigest()[:16])
                cur.execute(
                    """INSERT INTO notes (email, note_id, title, text, date, lang, code, flag, folder, subject, pinned, archived, edited, edited_at, subs, highlights, ts, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (email, note_id_val,
                     n.get("title",""), n.get("text",""), clean_date, n.get("lang",""), n.get("code",""),
                     n.get("flag","🇬🇧"), n.get("folder","General"), n.get("subject","General"),
                     bool(n.get("pinned", False)), bool(n.get("archived", False)),
                     is_edited, edited_at,
                     json.dumps(n.get("subs",[]) or []), json.dumps(n.get("highlights",[]) or []),
                     int(n.get("ts",0) or 0), datetime.now().isoformat())
                )
                # Auto-update public copy if this note was shared before
                try:
                    cur.execute(
                        """UPDATE public_notes 
                           SET title=%s, text=%s, folder=%s, subject=%s, date=%s, ts=%s
                           WHERE email=%s AND note_id=%s""",
                        (n.get("title",""), n.get("text",""), n.get("folder","General"), n.get("subject","General"), clean_date, int(n.get("ts",0) or 0), email, note_id_val)
                    )
                except Exception as e:
                    print(f"public update error: {e}")
                    pass
        return True
    except Exception as e:
        print(f"DB save notes error: {e}")
        return False

def get_email_from_token():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, "No token"
    token = auth.replace("Bearer ", "")
    try:
        import jwt
        decoded = jwt.decode(token, SECRET, algorithms=["HS256"])
        return decoded.get("email","").lower().strip(), None
    except Exception as e:
        return None, str(e)

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
    email, err = get_email_from_token()
    if not email:
        return jsonify({"error": "Invalid token", "details": err}), 401
    users = load_users()
    if email not in users:
        return jsonify({"error": "Account deleted"}), 401
    return jsonify({"email": email, "name": users[email]["name"]})

@app.route("/notes", methods=["GET", "POST", "OPTIONS"])
def notes_sync():
    if request.method == "OPTIONS":
        return "", 200
    email, err = get_email_from_token()
    if not email:
        return jsonify({"error": "Invalid token", "details": err}), 401
    if request.method == "GET":
        return jsonify({"notes": load_notes_for(email), "email": email})
    data = request.get_json(silent=True) or {}
    incoming = data.get("notes", [])
    if not isinstance(incoming, list):
        return jsonify({"error": "notes must be a list"}), 400
    ok = save_notes_for(email, incoming)
    if not ok:
        return jsonify({"error": "Could not save notes"}), 500
    return jsonify({"message": "Notes synced", "count": len(incoming)})

@app.route("/make-public", methods=["POST", "OPTIONS"])
def make_public():
    if request.method == "OPTIONS":
        return "", 200
    email, err = get_email_from_token()
    if not email:
        return jsonify({"error": "Invalid token", "details": err}), 401
    if not db:
        return jsonify({"error": "Database not connected"}), 500
    data = request.get_json(silent=True) or {}
    note_id = str(data.get("id") or data.get("note_id") or "").strip()
    if not note_id:
        return jsonify({"error": "Note id required"}), 400
    try:
        with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT note_id, title, text, folder, subject, date, ts FROM notes WHERE email=%s AND note_id=%s", (email, note_id))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Note not found"}), 404
            cur.execute("SELECT public_id FROM public_notes WHERE email=%s AND note_id=%s", (email, note_id))
            existing = cur.fetchone()
            if existing:
                return jsonify({"publicId": existing['public_id'], "alreadyPublic": True})
            public_id = secrets.token_urlsafe(6).replace('-','').replace('_','')[:8].lower()
            cur.execute("SELECT 1 FROM public_notes WHERE public_id=%s", (public_id,))
            while cur.fetchone():
                public_id = secrets.token_urlsafe(6).replace('-','').replace('_','')[:8].lower()
                cur.execute("SELECT 1 FROM public_notes WHERE public_id=%s", (public_id,))
            cur.execute(
                "INSERT INTO public_notes (public_id, email, note_id, title, text, folder, subject, date, ts, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (public_id, email, note_id, row['title'] or "", row['text'] or "", row['folder'] or "General", row['subject'] or "General", row['date'] or "", int(row['ts'] or 0), datetime.now().isoformat())
            )
            return jsonify({"publicId": public_id})
    except Exception as e:
        print(f"make-public error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/public-note/<public_id>", methods=["GET", "OPTIONS"])
def public_note(public_id):
    if request.method == "OPTIONS":
        return "", 200
    if not db:
        return jsonify({"error": "Database not connected"}), 500
    try:
        with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT public_id, title, text, folder, subject, date, ts, created_at FROM public_notes WHERE public_id=%s", (public_id.strip(),))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Note not found or not public"}), 404
            return jsonify({
                "publicId": row['public_id'],
                "title": row['title'] or "Untitled Note",
                "transcript": row['text'] or "",
                "text": row['text'] or "",
                "content": row['text'] or "",
                "folder": row['folder'] or "General",
                "subject": row['subject'] or "General",
                "date": row['date'] or "",
                "createdAt": row['created_at'] or row['date'] or "",
                "ts": row['ts'] or 0,
                "audioUrl": None
            })
    except Exception as e:
        print(f"public-note error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/delete-account", methods=["DELETE", "OPTIONS"])
def delete_account():
    if request.method == "OPTIONS":
        return "", 200
    email, err = get_email_from_token()
    if not email:
        return jsonify({"error": "Invalid or expired token", "details": err}), 401
    data = request.get_json(silent=True) or {}
    req_email = data.get("email", "").lower().strip() or email
    if req_email != email:
        return jsonify({"error": "You can only delete your own account"}), 403
    if not db:
        return jsonify({"error": "Database not connected"}), 500
    delete_user_notes(req_email)
    deleted = delete_user(req_email)
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
