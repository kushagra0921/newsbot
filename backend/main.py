from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import sqlite3
import hashlib

# ================== DB PATH ==================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "chat.db")

# ================== DB HELPER ==================

def execute_db(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, params)

    if fetch:
        rows = cur.fetchall()
        conn.close()
        return rows

    conn.commit()
    conn.close()

# ================== INIT TABLE ==================

execute_db("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT
)
""")

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

def hash_password(p: str):
    return hashlib.sha256(p.encode()).hexdigest()

def verify_password(p: str, h: str):
    return hash_password(p) == h

# ================== USER MEMORY ==================

user_memory = {}  # { user_id: "AI" | "TECH" | None }

# ================== NEWS ==================

NEWS_API_KEY = os.getenv("NEWS_API_KEY")

def fetch_news(query):
    if not NEWS_API_KEY:
        return []

    try:
        res = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 5,
                "apiKey": NEWS_API_KEY
            },
            timeout=5
        )
        data = res.json()
        return [a["title"] for a in data.get("articles", []) if a.get("title")]
    except:
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
    return {"status": "ok"}

# ================== AUTH ==================

@app.post("/register")
def register(data: AuthRequest):
    try:
        execute_db(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (data.username, hash_password(data.password))
        )
        return {"status": "registered"}
    except:
        return {"error": "Username already exists"}

@app.post("/login")
def login(data: AuthRequest):
    rows = execute_db(
        "SELECT id, password FROM users WHERE username=?",
        (data.username,),
        fetch=True
    )
    if not rows or not verify_password(data.password, rows[0]["password"]):
        return {"error": "Invalid credentials"}
    return {"user_id": rows[0]["id"]}

# ================== CHAT ==================

@app.post("/chat")
def chat(data: ChatRequest):
    if not data.message.strip():
        return {"reply": "Empty message."}

    user = execute_db(
        "SELECT id FROM users WHERE id=?",
        (data.user_id,),
        fetch=True
    )
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