"""
Authentication using Argon2 (recommended).
"""

import os
import datetime as dt
import sqlite3
from typing import Optional, Dict, Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import jwt

DB_PATH = os.getenv("ADCEA_AUTH_DB", os.path.join(os.getcwd(), "backend_auth.db"))
JWT_SECRET = os.getenv("ADCEA_JWT_SECRET", "change_this_secret")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

ph = PasswordHasher(time_cost=2, memory_cost=102400, parallelism=8)


def _get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


# --------------------------
#   Create new user
# --------------------------
def create_user(email: str, password: str):
    if not email or not password:
        raise ValueError("email and password required")

    password_hash = ph.hash(password)
    now = dt.datetime.utcnow().isoformat()

    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email.strip().lower(), password_hash, now),
        )
        conn.commit()
        uid = cur.lastrowid
    finally:
        conn.close()

    return {"id": uid, "email": email.strip().lower(), "created_at": now}


# --------------------------
#   Verify login
# --------------------------
def verify_user(email: str, password: str):
    conn = _get_conn()
    try:
        cur = conn.execute(
            "SELECT id, email, password_hash, created_at FROM users WHERE email=?",
            (email.strip().lower(),),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return None

    uid, email_db, hash_db, created_at = row

    try:
        ph.verify(hash_db, password)
    except VerifyMismatchError:
        return None
    except Exception:
        return None

    return {"id": uid, "email": email_db, "created_at": created_at}


# --------------------------
#   Issue JWT token
# --------------------------
def issue_access_token(user: Dict[str, Any]) -> str:
    now = dt.datetime.utcnow()
    exp = now + dt.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    if isinstance(token, bytes):
        token = token.decode()
    return token


# --------------------------
#   Decode JWT
# --------------------------
def decode_token(token: str):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None


def get_user_by_id(uid: int):
    conn = _get_conn()
    try:
        cur = conn.execute(
            "SELECT id, email, password_hash, created_at FROM users WHERE id=?",
            (uid,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return None

    uid, email, _, created_at = row
    return {"id": uid, "email": email, "created_at": created_at}
