from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import sqlite3
import hashlib

# ================== PATHS ==================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "chat.db")

# ================== DATABASE ==================

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

db = get_db()

db.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT
)
""")
db.commit()

# ================== APP ==================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================== MODELS ==================

class AuthRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    user_id: int
    message: str

# ================== AUTH HELPERS ==================

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

# ================== USER MEMORY ==================

# In-memory preference store
# { user_id: "AI" | "TECH" | None }
user_memory = {}

# ================== NEWS ==================

NEWS_API_KEY = os.getenv("NEWS_API_KEY")

def fetch_news(query: str):
    if not NEWS_API_KEY:
        return []

    try:
        response = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 5,
                "apiKey": NEWS_API_KEY
            },
            timeout=6
        )
        data = response.json()
        return [a["title"] for a in data.get("articles", []) if a.get("title")]
    except Exception:
        return []

def clean_headlines(headlines):
    cleaned = []
    for h in headlines:
        if " - " in h:
            h = h.split(" - ")[0]
        if len(h) > 90:
            h = h[:87] + "..."
        cleaned.append(h)
    return cleaned[:3]

def summarize(headlines, category):
    if len(headlines) < 2:
        return "No major updates right now."
    return f"{category} update: {headlines[0]} and {headlines[1]}."

# ================== HEALTH ==================

@app.get("/")
def health():
    return {"status": "Backend running 🚀"}

# ================== AUTH ==================

@app.post("/register")
def register(data: AuthRequest):
    try:
        db.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (data.username, hash_password(data.password))
        )
        db.commit()
        return {"status": "registered"}
    except sqlite3.IntegrityError:
        return {"error": "Username already exists"}

@app.post("/login")
def login(data: AuthRequest):
    row = db.execute(
        "SELECT id, password FROM users WHERE username=?",
        (data.username,)
    ).fetchone()

    if not row or not verify_password(data.password, row["password"]):
        return {"error": "Invalid credentials"}

    return {"user_id": row["id"]}

# ================== CHAT ==================

@app.post("/chat")
def chat(data: ChatRequest):
    if not data.message.strip():
        return {"reply": "Empty message."}

    user = db.execute(
        "SELECT id FROM users WHERE id=?",
        (data.user_id,)
    ).fetchone()

    if not user:
        return {"reply": "Invalid user. Please login again."}

    user_memory.setdefault(data.user_id, None)

    text = data.message.lower()
    pref = user_memory[data.user_id]

    if "only ai news" in text:
        user_memory[data.user_id] = "AI"
        reply = "Locked to AI news 🤖"

    elif "only tech news" in text:
        user_memory[data.user_id] = "TECH"
        reply = "Locked to tech news 💻"

    elif "reset" in text:
        user_memory[data.user_id] = None
        reply = "Preferences reset."

    elif pref == "AI":
        reply = summarize(clean_headlines(fetch_news("AI")), "AI")

    elif pref == "TECH":
        reply = summarize(clean_headlines(fetch_news("technology")), "TECH")

    elif "ai" in text:
        reply = summarize(clean_headlines(fetch_news("AI")), "AI")

    elif "tech" in text:
        reply = summarize(clean_headlines(fetch_news("technology")), "TECH")

    elif "news" in text:
        reply = summarize(clean_headlines(fetch_news("news")), "GENERAL")

    else:
        reply = "Ask for AI news, tech news, or general news."

    return {"reply": reply}

# ================== RUN ==================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
