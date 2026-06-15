from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from pypdf import PdfReader
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from ai import analyze_resume_with_gemini, generate_cover_letter_with_gemini
from db import DB_PATH, STATUSES, UPLOAD_DIR, get_db, get_settings, get_user_by_id, init_db, update_settings, upsert_google_user


load_dotenv()

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-this")

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to continue."

oauth = OAuth(app)
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

login_manager.login_view = "login"
login_manager.login_message = "Please sign in to continue."

DEFAULT_PASSWORD_HASH = "scrypt:32768:8:1$v74EpwsSofNeU0an$df6fb47fcc3f94572ab6748da5a1e292a7ccb0f0ba992df02ef24b3410b96dc8b37d1ebcac0b2fe9ce7fcf0c140c5ceb96071adff5a71e9bbebd1aba42769e3a"
ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx", ".txt"}

NAV_ITEMS = [
    {"endpoint": "dashboard", "icon": "layout-dashboard", "label": "Dashboard"},
    {"endpoint": "resume", "icon": "file-text", "label": "Resume Analyzer"},
    {"endpoint": "jobs", "icon": "briefcase-business", "label": "Job Matcher"},
    {"endpoint": "cover_letter", "icon": "pen-line", "label": "Cover Letter"},
    {"endpoint": "interview", "icon": "message-square", "label": "Interview Prep"},
    {"endpoint": "tracker", "icon": "kanban", "label": "App Tracker"},
    {"endpoint": "profile", "icon": "user", "label": "Profile"},
    {"endpoint": "settings", "icon": "settings", "label": "Settings"},
    {"endpoint": "admin", "icon": "shield", "label": "Admin"},
]

INTERVIEW_QUESTIONS = {
    "Technical": [
        {"difficulty": "Easy", "q": "Explain the difference between a stack and a queue.", "answer": "A stack is LIFO and works well for undo operations, recursion, and DFS. A queue is FIFO and fits scheduling, BFS, and ordered task processing."},
        {"difficulty": "Medium", "q": "What is the time complexity of QuickSort?", "answer": "Average complexity is O(n log n). Worst case is O(n^2), usually when pivots split the array poorly. Randomized pivots reduce that risk."},
        {"difficulty": "Hard", "q": "Design a URL shortener for 1 million requests per second.", "answer": "Use stateless app servers behind a load balancer, Redis for hot reads, durable storage for mappings, sharding, and a distributed ID generator."},
    ],
    "HR": [
        {"difficulty": "Easy", "q": "Tell me about yourself.", "answer": "Start with your current role, mention one strong project, connect your skills to the target role, and close with why this company."},
        {"difficulty": "Medium", "q": "Why do you want this company?", "answer": "Use a specific product, engineering problem, or mission point. Then connect it to your own work and interests."},
    ],
    "Behavioral": [
        {"difficulty": "Easy", "q": "Tell me about a tight deadline.", "answer": "Use STAR: situation, task, action, result. Show scope control, teamwork, and what shipped."},
        {"difficulty": "Medium", "q": "Describe a teammate conflict.", "answer": "Focus on listening, evidence-based decisions, and the shared goal rather than blaming the other person."},
    ],
    "Aptitude": [
        {"difficulty": "Easy", "q": "A train travels 360 km in 4 hours. How long for 540 km?", "answer": "Speed is 90 km/h, so 540 km takes 6 hours."},
        {"difficulty": "Medium", "q": "How many ways can ENGINEER be arranged?", "answer": "There are 8 letters with E repeated 3 times and N repeated 2 times, so 8! / (3! * 2!) = 3360."},
    ],
}


class User(UserMixin):
    def __init__(self, user_id: int, full_name: str = "", email: str = "", avatar_url: str = "") -> None:
        self.id = user_id
        self.full_name = full_name
        self.email = email
        self.avatar_url = avatar_url

    @classmethod
    def from_row(cls, row: dict[str, Any] | None) -> "User | None":
        if not row:
            return None
        return cls(int(row["id"]), row.get("full_name", ""), row.get("email", ""), row.get("avatar_url", ""))


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    return User.from_row(get_user_by_id(int(user_id)))


def get_active_user_id(user_id: int | None = None) -> int:
    if user_id is not None:
        return int(user_id)
    if current_user.is_authenticated:
        return int(current_user.get_id())
    return 1


def google_oauth_enabled() -> bool:
    return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))


def rows_to_jobs(rows) -> list[dict[str, Any]]:
    return [
        {
            "id": row["id"],
            "company": row["company"],
            "logo": row["logo"],
            "title": row["title"],
            "location": row["location"],
            "salary": row["salary"],
            "match": row["match_score"],
            "type": row["job_type"],
            "mode": row["mode"],
            "exp": row["experience"],
            "tags": json.loads(row["tags"]),
        }
        for row in rows
    ]


def row_to_application(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "company": row["company"],
        "role": row["role"],
        "status": row["status"],
        "date": date.fromisoformat(row["applied_on"]).strftime("%b %d, %Y"),
        "applied_on": row["applied_on"],
        "notes": row["notes"] or "",
        "match": row["match_score"],
    }


def get_applications(user_id: int | None = None) -> list[dict[str, Any]]:
    target_user_id = get_active_user_id(user_id)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM applications WHERE user_id = ? ORDER BY applied_on DESC, id DESC",
            (target_user_id,),
        ).fetchall()
    return [row_to_application(row) for row in rows]


def get_jobs() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY match_score DESC").fetchall()
    return rows_to_jobs(rows)


def get_profile(user_id: int | None = None) -> dict[str, Any]:
    target_user_id = get_active_user_id(user_id)
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (target_user_id,)).fetchone()
    return dict(row) if row else {}


def get_resume_history(limit: int = 12, user_id: int | None = None) -> list[dict[str, Any]]:
    target_user_id = get_active_user_id(user_id)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM resume_analyses WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (target_user_id, limit),
        ).fetchall()
    history = []
    for row in rows:
        item = dict(row)
        item["matched_skills"] = json.loads(item.get("matched_skills") or "[]")
        item["missing_skills"] = json.loads(item.get("missing_skills") or "[]")
        history.append(item)
    return history


def latest_resume_score(user_id: int | None = None) -> int:
    target_user_id = get_active_user_id(user_id)
    with get_db() as conn:
        row = conn.execute(
            "SELECT score FROM resume_analyses WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (target_user_id,),
        ).fetchone()
    return int(row["score"]) if row else 82


def build_dashboard_stats(applications: list[dict[str, Any]], resume_score: int) -> list[dict[str, str]]:
    total = len(applications)
    interviews = len([app_item for app_item in applications if app_item["status"] in {"Interview Scheduled", "Technical Round", "HR Round"}])
    selected = len([app_item for app_item in applications if app_item["status"] == "Selected"])
    cover_letters = max(1, total // 2)
    missing_skills = max(0, 12 - selected)
    return [
        {"label": "Resume Match Score", "value": f"{resume_score}%", "delta": "Latest AI analysis", "icon": "target", "tone": "indigo"},
        {"label": "Applications Submitted", "value": str(total), "delta": "Saved in SQLite", "icon": "briefcase", "tone": "emerald"},
        {"label": "Interviews Scheduled", "value": str(interviews), "delta": "Active pipeline", "icon": "calendar", "tone": "amber"},
        {"label": "Skills Missing", "value": str(missing_skills), "delta": "From target roles", "icon": "circle-alert", "tone": "rose"},
        {"label": "Cover Letters", "value": str(cover_letters), "delta": "AI-ready drafts", "icon": "pen-line", "tone": "sky"},
    ]


def extraction_quality_is_poor(text: str) -> bool:
    words = text.split()
    return len(words) < 40 or len(text.strip()) < 250


def extract_text_from_upload(upload) -> tuple[str, str, str | None]:
    if not upload or not upload.filename:
        return "", "", None
    filename = secure_filename(upload.filename)
    if not filename:
        return "", "", "No valid file name was found."
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_RESUME_EXTENSIONS:
        return "", filename, "Please upload a PDF, DOCX, or TXT resume file."

    path = UPLOAD_DIR / filename
    upload.save(path)

    try:
        if suffix == ".txt":
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
            return text, filename, None if text else "Could not extract text from this file. It may be a scanned or image-based PDF."
        if suffix == ".docx":
            from docx import Document

            doc = Document(path)
            text = "\n".join(paragraph.text for paragraph in doc.paragraphs).strip()
            return text, filename, None if text else "Could not extract text from this file. It may be a scanned or image-based PDF."
        if suffix == ".pdf":
            reader = PdfReader(str(path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
            if extraction_quality_is_poor(text):
                import pdfplumber

                with pdfplumber.open(path) as pdf:
                    fallback_text = "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
                if len(fallback_text) > len(text):
                    text = fallback_text
            return text, filename, None if text else "Could not extract text from this file. It may be a scanned or image-based PDF."
    except Exception:
        return "", filename, "Could not extract text from this file. It may be a scanned or image-based PDF."
    return "", filename, "Please upload a PDF, DOCX, or TXT resume file."


def save_resume_analysis(analysis: dict[str, Any], filename: str, job_description: str, user_id: int | None = None) -> int:
    target_user_id = get_active_user_id(user_id)
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO resume_analyses
            (user_id, filename, score, ats_score, keyword_score, matched_skills, missing_skills, strengths, suggestions, summary, job_description_preview)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_user_id,
                filename or "Typed resume text",
                int(analysis["score"]),
                int(analysis["ats_score"]),
                int(analysis["keyword_score"]),
                json.dumps(analysis.get("matched_skills", [])),
                json.dumps(analysis.get("missing_skills", [])),
                json.dumps(analysis.get("strengths", [])),
                json.dumps(analysis.get("suggestions", [])),
                analysis.get("summary", ""),
                job_description.strip()[:220],
            ),
        )
        return int(cursor.lastrowid)


def analyze_resume_text(resume_text: str, job_description: str, filename: str = "") -> dict[str, Any]:
    analysis = analyze_resume_with_gemini(resume_text, job_description)
    analysis["filename"] = filename or "Typed resume text"
    analysis["word_count"] = len(resume_text.split())
    return analysis


@app.context_processor
def inject_layout_data():
    profile = get_profile() if DB_PATH.exists() else {}
    settings = get_settings(get_active_user_id()) if DB_PATH.exists() else {}
    return {
        "nav_items": NAV_ITEMS,
        "current_year": date.today().year,
        "profile": profile,
        "settings": settings,
    }


@app.route("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    applications = get_applications()
    jobs = get_jobs()
    score = latest_resume_score()
    upcoming = [app_item for app_item in applications if app_item["status"] in {"Interview Scheduled", "Technical Round", "HR Round"}][:3]
    suggestions = [
        "Run a fresh Gemini resume analysis before applying to a new role.",
        "Move active interview applications to the right tracker stage.",
        "Generate a tailored cover letter before applying to recommended roles.",
    ]
    return render_template(
        "dashboard.html",
        title="Dashboard",
        stats=build_dashboard_stats(applications, score),
        applications=applications[:5],
        jobs=jobs[:3],
        upcoming=upcoming,
        suggestions=suggestions,
        latest_score=score,
    )


@app.route("/resume", methods=["GET", "POST"])
@login_required
def resume():
    if request.method == "POST":
        result, status = handle_resume_analysis()
        if status != 200:
            flash(result["error"], "error")
        else:
            flash("Resume analysis completed.", "success")
        return redirect(url_for("resume"))
    return render_template("resume.html", title="Resume Analyzer", history=get_resume_history())


@app.post("/api/resume/analyze")
@login_required
def api_resume_analyze():
    result, status = handle_resume_analysis()
    return jsonify(result), status


def handle_resume_analysis() -> tuple[dict[str, Any], int]:
    uploaded_text, filename, extraction_error = extract_text_from_upload(request.files.get("resume"))
    pasted_text = request.form.get("resume_text", "").strip()
    job_description = request.form.get("job_description", "").strip()
    resume_text = f"{uploaded_text}\n{pasted_text}".strip()
    if extraction_error and not pasted_text:
        return {"ok": False, "error": extraction_error}, 400
    if not resume_text:
        return {"ok": False, "error": "Upload a resume file or paste resume text before analyzing."}, 400
    if not job_description:
        return {"ok": False, "error": "Paste Job Description before running analysis."}, 400

    analysis = analyze_resume_text(resume_text, job_description, filename)
    analysis_id = save_resume_analysis(analysis, filename, job_description)
    analysis["id"] = analysis_id
    return {"ok": True, "analysis": analysis, "history": get_resume_history()}, 200


@app.route("/jobs")
@login_required
def jobs():
    query = request.args.get("q", "").lower()
    job_type = request.args.get("type", "All")
    mode = request.args.get("mode", "All")
    filtered = [
        job for job in get_jobs()
        if (not query or query in job["title"].lower() or query in job["company"].lower() or any(query in tag.lower() for tag in job["tags"]))
        and (job_type == "All" or job["type"] == job_type)
        and (mode == "All" or job["mode"] == mode)
    ]
    return render_template("jobs.html", title="Job Matcher", jobs=filtered, query=query, job_type=job_type, mode=mode)


@app.post("/jobs/<int:job_id>/apply")
@login_required
def apply_to_job(job_id: int):
    with get_db() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if job:
            conn.execute(
                """
                INSERT INTO applications (user_id, company, role, status, applied_on, notes, match_score)
                VALUES (?, ?, ?, 'Applied', ?, 'Added from Job Matcher', ?)
                """,
                (get_active_user_id(), job["company"], job["title"], date.today().isoformat(), job["match_score"]),
            )
    return redirect(url_for("tracker"))


@app.route("/cover-letter", methods=["GET", "POST"])
@login_required
def cover_letter():
    letter = None
    error = None
    if request.method == "POST":
        letter, error = generate_cover_letter_with_gemini(request.form)
    return render_template("cover_letter.html", title="Cover Letter", generated=letter is not None, letter=letter, error=error, form=request.form)


@app.post("/api/cover-letter")
@login_required
def api_cover_letter():
    letter, error = generate_cover_letter_with_gemini(request.form)
    return jsonify({"ok": True, "letter": letter, "warning": error})


@app.route("/interview")
@login_required
def interview():
    category = request.args.get("category", "Technical")
    if category not in INTERVIEW_QUESTIONS:
        category = "Technical"
    return render_template("interview.html", title="Interview Prep", category=category, questions=INTERVIEW_QUESTIONS)


@app.route("/tracker")
@login_required
def tracker():
    applications = get_applications()
    columns = {status: [] for status in STATUSES}
    for application in applications:
        columns.setdefault(application["status"], []).append(application)
    selected = len(columns["Selected"])
    rejected = len(columns["Rejected"])
    total = len(applications)
    stats = {
        "total": total,
        "selected": selected,
        "pending": max(0, total - selected - rejected),
        "success": round((selected / total) * 100) if total else 0,
    }
    return render_template("tracker.html", title="Application Tracker", columns=columns, stats=stats, statuses=STATUSES)


@app.post("/applications")
@login_required
def add_application():
    company = request.form.get("company", "").strip()
    role = request.form.get("role", "").strip()
    if company and role:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO applications (user_id, company, role, status, applied_on, notes, match_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    get_active_user_id(),
                    company,
                    role,
                    request.form.get("status", "Applied"),
                    request.form.get("applied_on") or date.today().isoformat(),
                    request.form.get("notes", "").strip(),
                    int(request.form.get("match_score") or 70),
                ),
            )
    return redirect(url_for("tracker"))


@app.post("/applications/<int:application_id>/status")
@login_required
def update_application_status(application_id: int):
    payload = request.get_json(silent=True) or request.form
    status = payload.get("status", "Applied")
    if status not in STATUSES:
        return jsonify({"ok": False, "error": "Invalid status"}), 400
    with get_db() as conn:
        conn.execute(
            "UPDATE applications SET status = ? WHERE id = ? AND user_id = ?",
            (status, application_id, get_active_user_id()),
        )
    return jsonify({"ok": True})


@app.post("/applications/<int:application_id>/delete")
@login_required
def delete_application(application_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM applications WHERE id = ? AND user_id = ?", (application_id, get_active_user_id()))
    return redirect(url_for("tracker"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        with get_db() as conn:
            conn.execute(
                """
                UPDATE users
                SET full_name = ?, email = ?, target_role = ?, graduation_year = ?, skills = ?,
                    linkedin_url = ?, github_url = ?, resume_link = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    request.form.get("full_name", "").strip(),
                    request.form.get("email", "").strip(),
                    request.form.get("target_role", "").strip(),
                    request.form.get("graduation_year", "").strip(),
                    request.form.get("skills", "").strip(),
                    request.form.get("linkedin_url", "").strip(),
                    request.form.get("github_url", "").strip(),
                    request.form.get("resume_link", "").strip(),
                    get_active_user_id(),
                ),
            )
        flash("Profile saved.", "success")
        return redirect(url_for("profile"))
    return render_template("profile.html", title="Profile", user_profile=get_profile())


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        update_settings(
            request.form.get("dark_mode") == "on",
            request.form.get("email_notifications") == "on",
            request.form.get("gemini_api_key", ""),
            get_active_user_id(),
        )
        flash("Settings saved.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", title="Settings", app_settings=get_settings())


@app.route("/admin")
@login_required
def admin():
    applications = get_applications()
    by_status = defaultdict(int)
    for application in applications:
        by_status[application["status"]] += 1
    description = f"SQLite database is active with {len(applications)} applications. Status counts: " + ", ".join(f"{status}: {by_status[status]}" for status in STATUSES)
    return render_template("simple_page.html", title="Admin", heading="Admin", description=description)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        password_hash = os.getenv("APP_PASSWORD", DEFAULT_PASSWORD_HASH)
        password = request.form.get("password", "")
        if check_password_hash(password_hash, password):
            login_user(User(1, "Your account", ""))
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Invalid password. Check APP_PASSWORD in your .env file."
    return render_template("login.html", title="Login", error=error, google_enabled=google_oauth_enabled())


@app.route("/login/google")
def login_google():
    if not google_oauth_enabled():
        flash("Google sign-in is not configured yet. Add your Google client credentials to the environment first.", "error")
        return redirect(url_for("login"))
    redirect_uri = url_for("google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route("/login/google/callback")
def google_callback():
    if not google_oauth_enabled():
        flash("Google sign-in is not configured yet.", "error")
        return redirect(url_for("login"))
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        flash("Google sign-in failed. Please try again.", "error")
        return redirect(url_for("login"))

    userinfo = token.get("userinfo")
    if not userinfo:
        userinfo = oauth.google.parse_id_token(token)

    if not userinfo:
        flash("Google sign-in failed. Please try again.", "error")
        return redirect(url_for("login"))

    user = upsert_google_user(
        google_id=str(userinfo.get("sub", "")),
        email=str(userinfo.get("email", "")),
        full_name=str(userinfo.get("name") or userinfo.get("email", "Google User")),
        avatar_url=str(userinfo.get("picture", "")),
    )
    login_user(User.from_row(user))
    return redirect(request.args.get("next") or url_for("dashboard"))


@app.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


init_db()


if __name__ == "__main__":
    app.run(debug=True)
