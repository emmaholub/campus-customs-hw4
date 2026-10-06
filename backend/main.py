from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

from fastapi import Cookie, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator
try:
    from .agent import AgentDeps, answer
    from .models import ChatReply, ChatRequest
except ImportError:
    from agent import AgentDeps, answer
    from models import ChatReply, ChatRequest

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("CAMPUS_CUSTOMS_DB", ROOT / "data" / "campus_customs.db"))
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
app = FastAPI(title="Campus Customs API")
allowed_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/images", StaticFiles(directory=ROOT / "data" / "products"), name="images")


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_history_table():
    with db() as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY(user_id) REFERENCES users(id))")
        connection.commit()


ensure_history_table()


def product(row):
    item = dict(row)
    for field in ("colors", "search_tags"):
        try: item[field] = json.loads(item[field])
        except (TypeError, json.JSONDecodeError): item[field] = []
    item["image_url"] = "/images/" + Path(item["image_file_path"]).name
    return item


@app.get("/health")
def health(): return {"status": "ok"}


@app.get("/api/products")
def products():
    with db() as connection:
        return [product(row) for row in connection.execute("SELECT * FROM catalogue ORDER BY name")]


@app.get("/api/products/{product_id}")
def one_product(product_id: str):
    with db() as connection:
        row = connection.execute("SELECT * FROM catalogue WHERE product_id = ?", (product_id,)).fetchone()
        if not row: raise HTTPException(404, "Product not found")
        item = product(row)
        inventory = connection.execute("SELECT size, quantity FROM inventory WHERE product_id = ? ORDER BY size", (product_id,)).fetchall()
        item["inventory"] = [dict(entry) for entry in inventory]
        return item


class Account(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_name(cls, value): return value.strip()


class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 210000)
    return "pbkdf2_sha256$210000$" + salt + "$" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        if stored.startswith("pbkdf2_sha256$"):
            parts = stored.split("$")
            if len(parts) == 4:
                _, rounds, salt, expected = parts
                iterations = int(rounds)
            else:
                _, salt, expected = parts
                iterations = 120000
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
            return hmac.compare_digest(actual, expected)
        return False
    except (ValueError, TypeError): return False


def session_value(user_id: int) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"user_id": user_id}).encode()).decode().rstrip("=")
    signature = hmac.new(SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return body + "." + signature


def set_session(response: Response, user_id: int):
    if not SESSION_SECRET: raise HTTPException(503, "SESSION_SECRET is not configured")
    response.set_cookie("campus_session", session_value(user_id), httponly=True, samesite="lax", secure=False, max_age=86400)


def current_user(session: str | None):
    if not SESSION_SECRET: return None
    if not session or "." not in session: return None
    body, signature = session.rsplit(".", 1)
    expected = hmac.new(SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected): return None
    try: user_id = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))["user_id"]
    except (ValueError, KeyError, json.JSONDecodeError): return None
    with db() as connection:
        return connection.execute("SELECT id, first_name, last_name, email FROM users WHERE id = ?", (user_id,)).fetchone()


@app.post("/api/auth/register")
def register(account: Account, response: Response):
    if account.password != account.confirm_password: raise HTTPException(400, "Passwords do not match")
    with db() as connection:
        try:
            cursor = connection.execute("INSERT INTO users (name, email, password_hash, first_name, last_name) VALUES (?, ?, ?, ?, ?)", (f"{account.first_name} {account.last_name}", str(account.email).lower(), hash_password(account.password), account.first_name, account.last_name))
            connection.commit()
        except sqlite3.IntegrityError: raise HTTPException(409, "An account with that email already exists")
    set_session(response, cursor.lastrowid)
    return {"user": {"id": cursor.lastrowid, "first_name": account.first_name, "last_name": account.last_name, "email": str(account.email).lower()}}


@app.post("/api/auth/login")
def login(account: Login, response: Response):
    with db() as connection: row = connection.execute("SELECT * FROM users WHERE lower(email) = lower(?)", (str(account.email),)).fetchone()
    if not row or not verify_password(account.password, row["password_hash"]): raise HTTPException(401, "Email or password is incorrect")
    set_session(response, row["id"])
    return {"user": {"id": row["id"], "first_name": row["first_name"] or row["name"], "last_name": row["last_name"] or "", "email": row["email"]}}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("campus_session"); return {"ok": True}


@app.post("/chat", response_model=ChatReply)
async def chat(request: ChatRequest, campus_session: str | None = Cookie(default=None)):
    try:
        user = current_user(campus_session)
        deps = AgentDeps(customer_name=(f"{user['first_name']} {user['last_name']}" if user else None), customer_email=(user["email"] if user else None), page_product_id=request.page_product_id, page_product_name=request.page_product_name)
        result = await answer(request.message.strip(), deps)
        if user:
            with db() as connection:
                connection.execute("INSERT INTO chat_history (user_id, role, content) VALUES (?, 'user', ?)", (user["id"], request.message.strip()))
                connection.execute("INSERT INTO chat_history (user_id, role, content) VALUES (?, 'assistant', ?)", (user["id"], result.message))
                connection.commit()
        return result
    except RuntimeError as error:
        raise HTTPException(503, str(error))
    except Exception as error:
        raise HTTPException(502, "The Campus Customs assistant is temporarily unavailable") from error


@app.get("/chat/history")
def chat_history(campus_session: str | None = Cookie(default=None)):
    user = current_user(campus_session)
    if not user: return {"messages": []}
    with db() as connection:
        rows = connection.execute("SELECT role, content, created_at FROM chat_history WHERE user_id = ? ORDER BY id", (user["id"],)).fetchall()
    return {"messages": [dict(row) for row in rows]}
