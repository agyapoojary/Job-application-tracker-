from __future__ import annotations

import os
import tempfile
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = Path(os.getenv("INSTANCE_DIR", "")).expanduser() if os.getenv("INSTANCE_DIR") else BASE_DIR / "instance"
if os.getenv("VERCEL") and not os.getenv("INSTANCE_DIR"):
    INSTANCE_DIR = Path(tempfile.gettempdir()) / "careerai-instance"
DB_PATH = INSTANCE_DIR / "careerai.db"
UPLOAD_DIR = INSTANCE_DIR / "uploads"

STATUSES = ["Applied", "Interview Scheduled", "Technical Round", "HR Round", "Selected", "Rejected"]


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]


def add_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column not in table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    INSTANCE_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                company TEXT NOT NULL,
                logo TEXT DEFAULT '',
                title TEXT NOT NULL,
                location TEXT DEFAULT '',
                salary TEXT DEFAULT '',
                match_score INTEGER DEFAULT 0,
                job_type TEXT DEFAULT '',
                mode TEXT DEFAULT '',
                experience TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                applied_on TEXT NOT NULL,
                notes TEXT DEFAULT '',
                match_score INTEGER DEFAULT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                upload_date TEXT DEFAULT CURRENT_TIMESTAMP,
                extracted_text TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS resume_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                resume_score INTEGER NOT NULL,
                ats_score INTEGER NOT NULL,
                strengths TEXT DEFAULT '[]',
                weaknesses TEXT DEFAULT '[]',
                missing_skills TEXT DEFAULT '[]',
                suggestions TEXT DEFAULT '[]',
                recommended_roles TEXT DEFAULT '[]',
                analysis_date TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                google_id TEXT UNIQUE,
                full_name TEXT DEFAULT '',
                email TEXT UNIQUE,
                avatar_url TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                target_role TEXT DEFAULT '',
                graduation_year TEXT DEFAULT '',
                skills TEXT DEFAULT '',
                education TEXT DEFAULT '',
                projects TEXT DEFAULT '',
                linkedin_url TEXT DEFAULT '',
                github_url TEXT DEFAULT '',
                portfolio_url TEXT DEFAULT '',
                resume_link TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE DEFAULT 1,
                dark_mode INTEGER DEFAULT 0,
                email_notifications INTEGER DEFAULT 0,
                gemini_api_key TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        migrate_existing_database(conn)
        remove_demo_rows(conn)
        conn.execute("INSERT OR IGNORE INTO users (id) VALUES (1)")
        conn.execute("INSERT OR IGNORE INTO settings (user_id, dark_mode, email_notifications, gemini_api_key) VALUES (1, 0, 1, '')")


def migrate_existing_database(conn: sqlite3.Connection) -> None:
    for table in ("jobs", "applications"):
        add_column(conn, table, "user_id", "INTEGER DEFAULT 1")
        add_column(conn, table, "created_at", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column(conn, "jobs", "logo", "TEXT DEFAULT ''")
    add_column(conn, "jobs", "location", "TEXT DEFAULT ''")
    add_column(conn, "jobs", "salary", "TEXT DEFAULT ''")
    add_column(conn, "jobs", "match_score", "INTEGER DEFAULT 0")
    add_column(conn, "jobs", "job_type", "TEXT DEFAULT ''")
    add_column(conn, "jobs", "mode", "TEXT DEFAULT ''")
    add_column(conn, "jobs", "experience", "TEXT DEFAULT ''")
    add_column(conn, "jobs", "tags", "TEXT DEFAULT '[]'")

    add_column(conn, "applications", "match_score", "INTEGER DEFAULT NULL")
    add_column(conn, "users", "google_id", "TEXT")
    add_column(conn, "users", "avatar_url", "TEXT DEFAULT ''")
    add_column(conn, "users", "phone", "TEXT DEFAULT ''")
    add_column(conn, "users", "education", "TEXT DEFAULT ''")
    add_column(conn, "users", "projects", "TEXT DEFAULT ''")
    add_column(conn, "users", "portfolio_url", "TEXT DEFAULT ''")
    add_column(conn, "settings", "user_id", "INTEGER DEFAULT 1")
    add_column(conn, "settings", "gemini_api_key", "TEXT DEFAULT ''")


def remove_demo_rows(conn: sqlite3.Connection) -> None:
    demo_companies = ("Google", "Microsoft", "Amazon", "Stripe", "Razorpay", "CRED", "Meesho", "Zepto")
    demo_apps = ("Atlassian", "Uber", "Google", "Microsoft", "Amazon", "Flipkart", "Razorpay", "Zomato")
    conn.execute(f"DELETE FROM jobs WHERE company IN ({','.join('?' for _ in demo_companies)})", demo_companies)
    conn.execute(f"DELETE FROM applications WHERE company IN ({','.join('?' for _ in demo_apps)})", demo_apps)


def ensure_user_settings(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO settings (user_id, dark_mode, email_notifications, gemini_api_key) VALUES (?, 0, 1, '')",
        (user_id,),
    )


def get_setting(key: str, default: str = "", user_id: int = 1) -> str:
    with get_db() as conn:
        ensure_user_settings(conn, user_id)
        row = conn.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,)).fetchone()
    if row is None or key not in row.keys():
        return default
    value = row[key]
    return default if value is None else str(value)


def get_settings(user_id: int = 1) -> dict:
    with get_db() as conn:
        ensure_user_settings(conn, user_id)
        row = conn.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else {"dark_mode": 0, "email_notifications": 0, "gemini_api_key": ""}


def update_settings(dark_mode: bool, email_notifications: bool, gemini_api_key: str, user_id: int = 1) -> None:
    with get_db() as conn:
        ensure_user_settings(conn, user_id)
        conn.execute(
            """
            UPDATE settings
            SET dark_mode = ?, email_notifications = ?, gemini_api_key = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (1 if dark_mode else 0, 1 if email_notifications else 0, gemini_api_key.strip(), user_id),
        )


def upsert_google_user(google_id: str, email: str, full_name: str, avatar_url: str = "") -> dict:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE google_id = ? OR email = ?", (google_id, email)).fetchone()
        if row:
            conn.execute(
                """
                UPDATE users
                SET google_id = ?, email = ?, full_name = ?, avatar_url = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (google_id, email, full_name, avatar_url, row["id"]),
            )
            user_id = row["id"]
        else:
            cursor = conn.execute(
                """
                INSERT INTO users (google_id, email, full_name, avatar_url)
                VALUES (?, ?, ?, ?)
                """,
                (google_id, email, full_name, avatar_url),
            )
            user_id = cursor.lastrowid
        ensure_user_settings(conn, int(user_id))
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(user)


def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None
