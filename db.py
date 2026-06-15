from __future__ import annotations

import json
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
DB_PATH = INSTANCE_DIR / "careerai.db"

STATUSES = ["Applied", "Interview Scheduled", "Technical Round", "HR Round", "Selected", "Rejected"]

SEED_JOBS = [
    {"company": "Google", "logo": "G", "title": "Software Engineer Intern", "location": "Bangalore, IN", "salary": "INR 80K-1.2L/mo", "match": 94, "type": "Internship", "mode": "Hybrid", "exp": "0-1 yr", "tags": ["Python", "ML", "GCP"]},
    {"company": "Microsoft", "logo": "M", "title": "SWE Intern - Azure", "location": "Hyderabad, IN", "salary": "INR 70K-90K/mo", "match": 88, "type": "Internship", "mode": "Hybrid", "exp": "0-1 yr", "tags": ["C#", ".NET", "Azure"]},
    {"company": "Amazon", "logo": "A", "title": "Software Development Engineer I", "location": "Bangalore, IN", "salary": "INR 20-28 LPA", "match": 81, "type": "Full Time", "mode": "On-site", "exp": "0-2 yr", "tags": ["Java", "AWS", "Microservices"]},
    {"company": "Stripe", "logo": "S", "title": "Frontend Engineer", "location": "Remote", "salary": "$120-150K/yr", "match": 91, "type": "Full Time", "mode": "Remote", "exp": "0-2 yr", "tags": ["React", "TypeScript", "Node.js"]},
    {"company": "Razorpay", "logo": "R", "title": "Backend Developer", "location": "Bangalore, IN", "salary": "INR 15-22 LPA", "match": 76, "type": "Full Time", "mode": "Hybrid", "exp": "1-3 yr", "tags": ["Go", "Kafka", "PostgreSQL"]},
    {"company": "CRED", "logo": "C", "title": "SDE Intern", "location": "Bangalore, IN", "salary": "INR 60K-80K/mo", "match": 85, "type": "Internship", "mode": "On-site", "exp": "0-1 yr", "tags": ["Kotlin", "Android", "Firebase"]},
    {"company": "Meesho", "logo": "M", "title": "Data Engineer", "location": "Bangalore, IN", "salary": "INR 12-18 LPA", "match": 72, "type": "Full Time", "mode": "Hybrid", "exp": "0-2 yr", "tags": ["Spark", "Python", "Airflow"]},
    {"company": "Zepto", "logo": "Z", "title": "SDE - Platform", "location": "Mumbai, IN", "salary": "INR 18-24 LPA", "match": 79, "type": "Full Time", "mode": "On-site", "exp": "1-2 yr", "tags": ["Node.js", "Redis", "Docker"]},
]

SEED_APPLICATIONS = [
    {"company": "Atlassian", "role": "SWE Intern", "status": "Applied", "applied_on": "2026-06-09", "notes": "Applied through campus portal", "match_score": 84},
    {"company": "Uber", "role": "Backend Dev", "status": "Applied", "applied_on": "2026-06-07", "notes": "", "match_score": 78},
    {"company": "Google", "role": "SWE Intern", "status": "Interview Scheduled", "applied_on": "2026-06-08", "notes": "Jun 12 @ 10AM", "match_score": 91},
    {"company": "Microsoft", "role": "SWE Intern", "status": "Interview Scheduled", "applied_on": "2026-06-05", "notes": "Jun 14 @ 2PM", "match_score": 87},
    {"company": "Amazon", "role": "SDE I", "status": "Technical Round", "applied_on": "2026-06-03", "notes": "2nd technical round pending", "match_score": 78},
    {"company": "Flipkart", "role": "Product Intern", "status": "HR Round", "applied_on": "2026-05-30", "notes": "", "match_score": 82},
    {"company": "Razorpay", "role": "Backend Intern", "status": "Selected", "applied_on": "2026-05-20", "notes": "Offer letter received", "match_score": 89},
    {"company": "Zomato", "role": "SWE", "status": "Rejected", "applied_on": "2026-05-25", "notes": "", "match_score": 65},
]


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    INSTANCE_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                logo TEXT NOT NULL,
                title TEXT NOT NULL,
                location TEXT NOT NULL,
                salary TEXT NOT NULL,
                match_score INTEGER NOT NULL,
                job_type TEXT NOT NULL,
                mode TEXT NOT NULL,
                experience TEXT NOT NULL,
                tags TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                applied_on TEXT NOT NULL,
                notes TEXT DEFAULT '',
                match_score INTEGER DEFAULT 70,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS resume_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                filename TEXT,
                score INTEGER NOT NULL,
                ats_score INTEGER NOT NULL,
                keyword_score INTEGER DEFAULT 0,
                matched_skills TEXT DEFAULT '[]',
                missing_skills TEXT DEFAULT '[]',
                strengths TEXT DEFAULT '[]',
                suggestions TEXT DEFAULT '[]',
                summary TEXT DEFAULT '',
                job_description_preview TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                google_id TEXT UNIQUE,
                full_name TEXT DEFAULT '',
                email TEXT UNIQUE,
                avatar_url TEXT DEFAULT '',
                target_role TEXT DEFAULT '',
                graduation_year TEXT DEFAULT '',
                skills TEXT DEFAULT '',
                linkedin_url TEXT DEFAULT '',
                github_url TEXT DEFAULT '',
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
        migrate_for_multi_user(conn)
        conn.execute("DELETE FROM jobs WHERE company IN ('Google', 'Microsoft', 'Amazon', 'Stripe', 'Razorpay', 'CRED', 'Meesho', 'Zepto')")
        conn.execute("DELETE FROM applications WHERE company IN ('Atlassian', 'Uber', 'Google', 'Microsoft', 'Amazon', 'Flipkart', 'Razorpay', 'Zomato')")
        conn.execute("INSERT OR IGNORE INTO users (id) VALUES (1)")
        conn.execute("INSERT OR IGNORE INTO settings (user_id, dark_mode, email_notifications, gemini_api_key) VALUES (1, 0, 1, '')")


def table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]


def migrate_for_multi_user(conn: sqlite3.Connection) -> None:
    user_columns = table_columns(conn, "users")
    if user_columns and "google_id" not in user_columns:
        existing = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
        conn.execute("ALTER TABLE users RENAME TO users_single_backup")
        conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                google_id TEXT UNIQUE,
                full_name TEXT DEFAULT '',
                email TEXT UNIQUE,
                avatar_url TEXT DEFAULT '',
                target_role TEXT DEFAULT '',
                graduation_year TEXT DEFAULT '',
                skills TEXT DEFAULT '',
                linkedin_url TEXT DEFAULT '',
                github_url TEXT DEFAULT '',
                resume_link TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        if existing:
            conn.execute(
                """
                INSERT INTO users
                (id, full_name, email, target_role, graduation_year, skills, linkedin_url, github_url, resume_link, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    existing["full_name"] or "CareerAI User",
                    existing["email"] or "local@careerai.dev",
                    existing["target_role"] or "",
                    existing["graduation_year"] or "",
                    existing["skills"] or "",
                    existing["linkedin_url"] or "",
                    existing["github_url"] or "",
                    existing["resume_link"] or "",
                    existing["updated_at"],
                ),
            )

    setting_columns = table_columns(conn, "settings")
    if setting_columns and "user_id" not in setting_columns:
        existing_settings = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        conn.execute("ALTER TABLE settings RENAME TO settings_single_backup")
        conn.executescript(
            """
            CREATE TABLE settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE DEFAULT 1,
                dark_mode INTEGER DEFAULT 0,
                email_notifications INTEGER DEFAULT 0,
                gemini_api_key TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        if existing_settings:
            conn.execute(
                """
                INSERT INTO settings (user_id, dark_mode, email_notifications, gemini_api_key, updated_at)
                VALUES (1, ?, ?, ?, ?)
                """,
                (
                    existing_settings["dark_mode"],
                    existing_settings["email_notifications"],
                    existing_settings["gemini_api_key"] or "",
                    existing_settings["updated_at"],
                ),
            )

    analysis_columns = table_columns(conn, "resume_analyses")
    if analysis_columns and "user_id" not in analysis_columns:
        conn.execute("ALTER TABLE resume_analyses ADD COLUMN user_id INTEGER DEFAULT 1")

    application_columns = table_columns(conn, "applications")
    if application_columns and "user_id" not in application_columns:
        conn.execute("ALTER TABLE applications ADD COLUMN user_id INTEGER DEFAULT 1")


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


def ensure_user_settings(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO settings (user_id, dark_mode, email_notifications, gemini_api_key) VALUES (?, 0, 1, '')",
        (user_id,),
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
