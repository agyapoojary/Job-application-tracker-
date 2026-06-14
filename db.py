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
                id INTEGER PRIMARY KEY CHECK (id = 1),
                full_name TEXT DEFAULT '',
                email TEXT DEFAULT '',
                target_role TEXT DEFAULT '',
                graduation_year TEXT DEFAULT '',
                skills TEXT DEFAULT '',
                linkedin_url TEXT DEFAULT '',
                github_url TEXT DEFAULT '',
                resume_link TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                dark_mode INTEGER DEFAULT 0,
                email_notifications INTEGER DEFAULT 0,
                gemini_api_key TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        if conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0:
            conn.executemany(
                """
                INSERT INTO jobs (company, logo, title, location, salary, match_score, job_type, mode, experience, tags)
                VALUES (:company, :logo, :title, :location, :salary, :match, :type, :mode, :exp, :tags)
                """,
                [{**job, "tags": json.dumps(job["tags"])} for job in SEED_JOBS],
            )
        if conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 0:
            conn.executemany(
                """
                INSERT INTO applications (company, role, status, applied_on, notes, match_score)
                VALUES (:company, :role, :status, :applied_on, :notes, :match_score)
                """,
                SEED_APPLICATIONS,
            )
        conn.execute("INSERT OR IGNORE INTO users (id, full_name, email, target_role, graduation_year, skills) VALUES (1, 'Aryan Kumar', 'aryan@iit.ac.in', 'Software Engineer Intern', '2027', 'Python, Flask, SQL')")
        conn.execute("INSERT OR IGNORE INTO settings (id, dark_mode, email_notifications, gemini_api_key) VALUES (1, 0, 1, '')")


def get_setting(key: str, default: str = "") -> str:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    if row is None or key not in row.keys():
        return default
    value = row[key]
    return default if value is None else str(value)


def get_settings() -> dict:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return dict(row) if row else {"dark_mode": 0, "email_notifications": 0, "gemini_api_key": ""}


def update_settings(dark_mode: bool, email_notifications: bool, gemini_api_key: str) -> None:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE settings
            SET dark_mode = ?, email_notifications = ?, gemini_api_key = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (1 if dark_mode else 0, 1 if email_notifications else 0, gemini_api_key.strip()),
        )

