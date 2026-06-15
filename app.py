from __future__ import annotations

import json
import logging
import os
import re
import uuid
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

from ai import AIError, analyze_resume, generate_cover_letter_with_gemini, match_job_description
from db import DB_PATH, STATUSES, UPLOAD_DIR, get_db, get_settings, get_user_by_id, init_db, update_settings, upsert_google_user


load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOGGER = logging.getLogger(__name__)

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

DEFAULT_PASSWORD_HASH = "scrypt:32768:8:1$v74EpwsSofNeU0an$df6fb47fcc3f94572ab6748da5a1e292a7ccb0f0ba992df02ef24b3410b96dc8b37d1ebcac0b2fe9ce7fcf0c140c5ceb96071adff5a71e9bbebd1aba42769e3a"
ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx"}

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
        {"difficulty": "Easy", "q": "Explain the difference between a stack and a queue.", "answer": "A stack is LIFO and a queue is FIFO."},
        {"difficulty": "Medium", "q": "How would you optimize a slow database-backed endpoint?", "answer": "Measure the query plan, add targeted indexes, reduce transferred data, cache where suitable, and keep correctness tests around the change."},
    ],
    "HR": [
        {"difficulty": "Easy", "q": "Tell me about yourself.", "answer": "Connect your current work, one relevant achievement, and why the role fits your direction."},
        {"difficulty": "Medium", "q": "Why are you interested in this role?", "answer": "Use specific responsibilities from the role and connect them to your skills and goals."},
    ],
    "Behavioral": [
        {"difficulty": "Easy", "q": "Tell me about a tight deadline.", "answer": "Use situation, task, action, and result, with one clear lesson learned."},
        {"difficulty": "Medium", "q": "Describe a conflict with a teammate.", "answer": "Focus on listening, evidence, and the shared outcome."},
    ],
}

SKILL_TERMS = {
    "python", "java", "javascript", "typescript", "c++", "c#", "sql", "sqlite", "postgresql", "mysql",
    "flask", "django", "fastapi", "react", "node.js", "express", "html", "css", "tailwind",
    "aws", "azure", "gcp", "docker", "kubernetes", "git", "github", "linux", "rest api",
    "machine learning", "data analysis", "pandas", "numpy", "tensorflow", "pytorch", "excel",
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


def parse_json_list(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed if str(item).strip()] if isinstance(parsed, list) else []


def get_profile(user_id: int | None = None) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (get_active_user_id(user_id),)).fetchone()
    return dict(row) if row else {}


def get_applications(user_id: int | None = None) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM applications WHERE user_id = ? ORDER BY applied_on DESC, id DESC",
            (get_active_user_id(user_id),),
        ).fetchall()
    applications = []
    for row in rows:
        item = dict(row)
        item["date"] = date.fromisoformat(item["applied_on"]).strftime("%b %d, %Y")
        applications.append(item)
    return applications


def get_jobs() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC, id DESC").fetchall()
    jobs = []
    for row in rows:
        item = dict(row)
        item["match"] = item.get("match_score")
        item["type"] = item.get("job_type") or ""
        item["exp"] = item.get("experience") or ""
        item["tags"] = parse_json_list(item.get("tags"))
        jobs.append(item)
    return jobs


def latest_resume(user_id: int | None = None) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM resumes WHERE user_id = ? ORDER BY upload_date DESC, id DESC LIMIT 1",
            (get_active_user_id(user_id),),
        ).fetchone()
    return dict(row) if row else None


def latest_analysis(user_id: int | None = None) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM resume_analysis WHERE user_id = ? ORDER BY analysis_date DESC, id DESC LIMIT 1",
            (get_active_user_id(user_id),),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    for key in ("strengths", "weaknesses", "missing_skills", "suggestions", "recommended_roles"):
        item[key] = parse_json_list(item.get(key))
    return item


def get_resume_history(limit: int = 12, user_id: int | None = None) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT ra.*, r.filename
            FROM resume_analysis ra
            LEFT JOIN resumes r ON r.user_id = ra.user_id
              AND r.upload_date <= ra.analysis_date
            WHERE ra.user_id = ?
            GROUP BY ra.id
            ORDER BY ra.analysis_date DESC, ra.id DESC
            LIMIT ?
            """,
            (get_active_user_id(user_id), limit),
        ).fetchall()
    history = []
    for row in rows:
        item = dict(row)
        for key in ("strengths", "weaknesses", "missing_skills", "suggestions", "recommended_roles"):
            item[key] = parse_json_list(item.get(key))
        history.append(item)
    return history


def extract_resume_text(file_path: str | Path) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if len(text.split()) < 40:
            import pdfplumber

            with pdfplumber.open(path) as pdf:
                fallback_text = "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
            if len(fallback_text) > len(text):
                text = fallback_text
        return text
    if suffix == ".docx":
        from docx import Document

        doc = Document(path)
        return "\n".join(paragraph.text for paragraph in doc.paragraphs).strip()
    raise ValueError("Unsupported resume file type.")


def save_uploaded_resume(upload) -> tuple[int, str, str]:
    if not upload or not upload.filename:
        raise ValueError("Upload a PDF or DOCX resume.")
    original = secure_filename(upload.filename)
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_RESUME_EXTENSIONS:
        raise ValueError("Please upload a PDF or DOCX resume file.")
    stored_name = f"user-{get_active_user_id()}-{uuid.uuid4().hex}{suffix}"
    path = UPLOAD_DIR / stored_name
    upload.save(path)
    text = extract_resume_text(path)
    if not text:
        raise ValueError("Could not extract text from this resume. Upload a text-based PDF or DOCX file.")
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO resumes (user_id, filename, extracted_text) VALUES (?, ?, ?)",
            (get_active_user_id(), stored_name, text),
        )
        resume_id = int(cursor.lastrowid)
    return resume_id, stored_name, text


def save_resume_analysis(analysis: dict[str, Any]) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO resume_analysis
            (user_id, resume_score, ats_score, strengths, weaknesses, missing_skills, suggestions, recommended_roles)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                get_active_user_id(),
                int(analysis["resume_score"]),
                int(analysis["ats_score"]),
                json.dumps(analysis.get("strengths", [])),
                json.dumps(analysis.get("weaknesses", [])),
                json.dumps(analysis.get("missing_skills", [])),
                json.dumps(analysis.get("suggestions", [])),
                json.dumps(analysis.get("recommended_roles", [])),
            ),
        )
    return int(cursor.lastrowid)


def extract_skills_from_text(text: str, profile_skills: str = "") -> list[str]:
    haystack = f"{text}\n{profile_skills}".lower()
    found = {skill for skill in SKILL_TERMS if re.search(rf"(?<![\w+.#-]){re.escape(skill)}(?![\w+.#-])", haystack)}
    for skill in re.split(r"[,;\n]", profile_skills or ""):
        cleaned = skill.strip()
        if cleaned:
            found.add(cleaned.lower())
    return sorted({skill.upper() if skill in {"sql", "aws", "gcp"} else skill.title() for skill in found})


def profile_completion(profile: dict[str, Any], resume_row: dict[str, Any] | None, skills_found: list[str]) -> int:
    fields = [
        profile.get("full_name"),
        profile.get("email"),
        profile.get("phone"),
        resume_row,
        skills_found,
        profile.get("education") or profile.get("graduation_year"),
        profile.get("projects"),
        profile.get("linkedin_url"),
        profile.get("portfolio_url"),
    ]
    return round((sum(1 for field in fields if field) / len(fields)) * 100)


def build_dashboard_stats(profile: dict[str, Any], resume_row: dict[str, Any] | None, analysis: dict[str, Any] | None) -> tuple[list[dict[str, str]], int, list[str]]:
    resume_text = resume_row.get("extracted_text", "") if resume_row else ""
    skills = extract_skills_from_text(resume_text, profile.get("skills", ""))
    completion = profile_completion(profile, resume_row, skills)
    stats = [
        {"label": "Resume Score", "value": f"{analysis['resume_score']}%" if analysis else "N/A", "delta": "Latest AI analysis" if analysis else "Upload required", "icon": "target", "tone": "indigo"},
        {"label": "ATS Score", "value": f"{analysis['ats_score']}%" if analysis else "N/A", "delta": "Latest AI analysis" if analysis else "Upload required", "icon": "scan-text", "tone": "emerald"},
        {"label": "Skills Found", "value": str(len(skills)), "delta": "From resume and profile", "icon": "badge-check", "tone": "sky"},
        {"label": "Missing Skills", "value": str(len(analysis["missing_skills"])) if analysis else "N/A", "delta": "From latest AI analysis" if analysis else "Upload required", "icon": "circle-alert", "tone": "rose"},
        {"label": "Recommended Roles", "value": str(len(analysis["recommended_roles"])) if analysis else "N/A", "delta": "From latest AI analysis" if analysis else "Upload required", "icon": "briefcase-business", "tone": "amber"},
        {"label": "Resume Upload Date", "value": resume_row["upload_date"].split(" ")[0] if resume_row else "N/A", "delta": "Latest uploaded resume" if resume_row else "Upload required", "icon": "calendar", "tone": "indigo"},
    ]
    return stats, completion, skills


@app.context_processor
def inject_layout_data():
    profile = get_profile() if DB_PATH.exists() else {}
    settings = get_settings(get_active_user_id()) if DB_PATH.exists() else {}
    return {"nav_items": NAV_ITEMS, "current_year": date.today().year, "profile": profile, "settings": settings}


@app.route("/")
def home():
    return redirect(url_for("dashboard" if current_user.is_authenticated else "login"))


@app.route("/dashboard")
@login_required
def dashboard():
    profile = get_profile()
    resume_row = latest_resume()
    analysis = latest_analysis()
    stats, completion, skills = build_dashboard_stats(profile, resume_row, analysis)
    applications = get_applications()
    upcoming = [app_item for app_item in applications if app_item["status"] in {"Interview Scheduled", "Technical Round", "HR Round"}][:3]
    return render_template(
        "dashboard.html",
        title="Dashboard",
        stats=stats,
        applications=applications[:5],
        upcoming=upcoming,
        latest_analysis=analysis,
        latest_resume=resume_row,
        profile_completion=completion,
        skills_found=skills,
        suggestions=analysis["suggestions"] if analysis else [],
        recommended_roles=analysis["recommended_roles"] if analysis else [],
    )


@app.route("/resume", methods=["GET", "POST"])
@login_required
def resume():
    if request.method == "POST":
        result, status = handle_resume_analysis()
        flash("Resume analysis completed." if status == 200 else result["error"], "success" if status == 200 else "error")
        return redirect(url_for("resume"))
    return render_template("resume.html", title="Resume Analyzer", history=get_resume_history(), latest_analysis=latest_analysis())


@app.post("/api/resume/analyze")
@login_required
def api_resume_analyze():
    result, status = handle_resume_analysis()
    return jsonify(result), status


def handle_resume_analysis() -> tuple[dict[str, Any], int]:
    try:
        _, filename, resume_text = save_uploaded_resume(request.files.get("resume"))
        analysis = analyze_resume(resume_text)
        analysis_id = save_resume_analysis(analysis)
    except (ValueError, AIError) as exc:
        return {"ok": False, "error": str(exc)}, 400
    except Exception as exc:
        LOGGER.exception("Unexpected resume analysis error")
        return {"ok": False, "error": "Resume analysis failed. Check logs for details."}, 500
    analysis["id"] = analysis_id
    analysis["filename"] = filename
    return {"ok": True, "analysis": analysis, "history": get_resume_history()}, 200


@app.route("/jobs", methods=["GET", "POST"])
@login_required
def jobs():
    match_result = None
    error = None
    job_description = ""
    if request.method == "POST":
        job_description = request.form.get("job_description", "").strip()
        resume_row = latest_resume()
        if not resume_row:
            error = "Upload your resume to receive AI-powered job matching."
        elif not job_description:
            error = "Paste a job description before running the matcher."
        else:
            try:
                match_result = match_job_description(resume_row["extracted_text"], job_description)
            except AIError as exc:
                error = str(exc)
    query = request.args.get("q", "").lower()
    filtered = [job for job in get_jobs() if not query or query in job["title"].lower() or query in job["company"].lower()]
    return render_template("jobs.html", title="Job Matcher", jobs=filtered, query=query, match_result=match_result, error=error, job_description=job_description, has_resume=latest_resume() is not None)


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
    return jsonify({"ok": letter is not None, "letter": letter or "", "error": error})


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
    stats = {"total": total, "selected": selected, "pending": max(0, total - selected - rejected), "success": round((selected / total) * 100) if total else 0}
    return render_template("tracker.html", title="Application Tracker", columns=columns, stats=stats, statuses=STATUSES)


@app.post("/applications")
@login_required
def add_application():
    company = request.form.get("company", "").strip()
    role = request.form.get("role", "").strip()
    if company and role:
        raw_score = request.form.get("match_score", "").strip()
        match_score = int(raw_score) if raw_score.isdigit() else None
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO applications (user_id, company, role, status, applied_on, notes, match_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (get_active_user_id(), company, role, request.form.get("status", "Applied"), request.form.get("applied_on") or date.today().isoformat(), request.form.get("notes", "").strip(), match_score),
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
        conn.execute("UPDATE applications SET status = ? WHERE id = ? AND user_id = ?", (status, application_id, get_active_user_id()))
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
                SET full_name = ?, email = ?, phone = ?, target_role = ?, graduation_year = ?, skills = ?,
                    education = ?, projects = ?, linkedin_url = ?, github_url = ?, portfolio_url = ?,
                    resume_link = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    request.form.get("full_name", "").strip(),
                    request.form.get("email", "").strip(),
                    request.form.get("phone", "").strip(),
                    request.form.get("target_role", "").strip(),
                    request.form.get("graduation_year", "").strip(),
                    request.form.get("skills", "").strip(),
                    request.form.get("education", "").strip(),
                    request.form.get("projects", "").strip(),
                    request.form.get("linkedin_url", "").strip(),
                    request.form.get("github_url", "").strip(),
                    request.form.get("portfolio_url", "").strip(),
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
        update_settings(request.form.get("dark_mode") == "on", request.form.get("email_notifications") == "on", request.form.get("gemini_api_key", ""), get_active_user_id())
        flash("Settings saved.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", title="Settings", app_settings=get_settings(get_active_user_id()))


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
            with get_db() as conn:
                conn.execute("INSERT OR IGNORE INTO users (id) VALUES (1)")
            login_user(User(1, "Your account", request.form.get("email", "")))
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Invalid password. Check APP_PASSWORD in your .env file."
    return render_template("login.html", title="Login", error=error, google_enabled=google_oauth_enabled())


@app.route("/login/google")
def login_google():
    if not google_oauth_enabled():
        flash("Google sign-in is not configured yet. Add your Google client credentials to the environment first.", "error")
        return redirect(url_for("login"))
    session["oauth_state"] = uuid.uuid4().hex
    return oauth.google.authorize_redirect(url_for("google_callback", _external=True))


@app.route("/login/google/callback")
def google_callback():
    if not google_oauth_enabled():
        flash("Google sign-in is not configured yet.", "error")
        return redirect(url_for("login"))
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        LOGGER.exception("Google sign-in failed")
        flash("Google sign-in failed. Please try again.", "error")
        return redirect(url_for("login"))
    userinfo = token.get("userinfo") or oauth.google.parse_id_token(token)
    if not userinfo:
        flash("Google sign-in failed. Please try again.", "error")
        return redirect(url_for("login"))
    user = upsert_google_user(str(userinfo.get("sub", "")), str(userinfo.get("email", "")), str(userinfo.get("name") or userinfo.get("email", "")), str(userinfo.get("picture", "")))
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
