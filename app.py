from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for
from pypdf import PdfReader
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
DB_PATH = INSTANCE_DIR / "careerai.db"

STATUSES = ["Applied", "Interview Scheduled", "Technical Round", "HR Round", "Selected", "Rejected"]
SKILL_KEYWORDS = [
    "python", "flask", "django", "sql", "postgresql", "mysql", "sqlite", "javascript",
    "typescript", "react", "node", "aws", "gcp", "azure", "docker", "kubernetes",
    "redis", "graphql", "ci/cd", "machine learning", "tensorflow", "pandas", "java",
    "c++", "git", "system design", "microservices", "api", "html", "css",
]

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
app.config["SECRET_KEY"] = "dev-secret-change-this"

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


def rows_to_jobs(rows: list[sqlite3.Row]) -> list[dict]:
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


def row_to_application(row: sqlite3.Row) -> dict:
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


def get_applications() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM applications ORDER BY applied_on DESC, id DESC").fetchall()
    return [row_to_application(row) for row in rows]


def get_jobs() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY match_score DESC").fetchall()
    return rows_to_jobs(rows)


def build_dashboard_stats(applications: list[dict], resume_score: int = 82) -> list[dict]:
    total = len(applications)
    interviews = len([app for app in applications if app["status"] in {"Interview Scheduled", "Technical Round", "HR Round"}])
    selected = len([app for app in applications if app["status"] == "Selected"])
    cover_letters = max(1, total // 2)
    missing_skills = max(0, 12 - selected)
    return [
        {"label": "Resume Match Score", "value": f"{resume_score}%", "delta": "Based on latest analysis", "icon": "target", "tone": "indigo"},
        {"label": "Applications Submitted", "value": str(total), "delta": "Saved in SQLite", "icon": "briefcase", "tone": "emerald"},
        {"label": "Interviews Scheduled", "value": str(interviews), "delta": "Active pipeline", "icon": "calendar", "tone": "amber"},
        {"label": "Skills Missing", "value": str(missing_skills), "delta": "From target job keywords", "icon": "circle-alert", "tone": "rose"},
        {"label": "Cover Letters", "value": str(cover_letters), "delta": "Generated drafts", "icon": "pen-line", "tone": "sky"},
    ]


def analyze_resume_text(resume_text: str, job_description: str, filename: str = "", extraction_note: str = "") -> dict:
    combined_resume = f"{resume_text} {filename}".lower()
    job_text = job_description.lower()
    required = [skill for skill in SKILL_KEYWORDS if skill in job_text]
    if not required:
        required = ["python", "sql", "git", "api", "system design", "communication"]
    matched = [skill for skill in required if skill in combined_resume]
    missing = [skill for skill in required if skill not in matched]
    keyword_score = round((len(matched) / len(required)) * 100) if required else 70
    word_count = len(resume_text.split())
    quality_bonus = min(18, word_count // 35)
    score = min(98, max(45, keyword_score + quality_bonus))
    ats_score = min(96, max(50, score + 7 if filename.lower().endswith((".pdf", ".docx", ".txt")) else score - 3))
    detected_sections = [
        section for section in ["education", "experience", "projects", "skills", "certifications", "achievements"]
        if section in combined_resume
    ]
    section_suggestion = (
        f"Detected sections: {', '.join(section.title() for section in detected_sections)}."
        if detected_sections
        else "Add clear section headings such as Skills, Projects, Experience, and Education."
    )
    return {
        "score": score,
        "ats_score": ats_score,
        "keyword_score": keyword_score,
        "word_count": word_count,
        "matched": [skill.title() for skill in matched],
        "missing": [skill.title() for skill in missing] or ["Add more job-specific keywords"],
        "strengths": [
            "Includes relevant job keywords" if matched else "Clear upload and job description received",
            "ATS-friendly file type" if filename.lower().endswith((".pdf", ".docx", ".txt")) else "Use PDF, DOCX, or TXT for best ATS results",
            "Good length for automated screening" if word_count > 120 else "Concise resume content",
            section_suggestion,
        ],
        "suggestions": [
            f"Add these missing skills where truthful: {', '.join(skill.title() for skill in missing[:5])}" if missing else "Your resume covers the main requested skills.",
            "Quantify project impact with numbers such as users, latency, revenue, or accuracy.",
            "Mirror the exact role title and top keywords from the job description.",
        ],
        "filename": filename or "Typed resume text",
        "extraction_note": extraction_note,
    }


def extract_text_from_upload(upload) -> tuple[str, str, str]:
    if not upload or not upload.filename:
        return "", "", "No file uploaded. Paste resume text or choose a PDF/TXT file."
    filename = secure_filename(upload.filename)
    if not filename:
        return "", "", "No valid file name was found."
    path = UPLOAD_DIR / filename
    upload.save(path)
    if path.suffix.lower() == ".txt":
        text = path.read_text(encoding="utf-8", errors="ignore")
        return text, filename, f"Read {len(text.split())} words from TXT."
    if path.suffix.lower() == ".pdf":
        try:
            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages).strip()
            if text:
                return text, filename, f"Read {len(text.split())} words from {len(reader.pages)} PDF page(s)."
            return "", filename, "PDF uploaded, but no selectable text was found. Try a text-based PDF or paste resume text below."
        except Exception as exc:
            return "", filename, f"PDF uploaded, but reading failed: {exc}"
    return "", filename, "File uploaded. For automatic reading, use PDF or TXT."


def make_cover_letter(form) -> str:
    name = form.get("name", "Aryan Kumar").strip() or "Aryan Kumar"
    company = form.get("company", "the company").strip() or "the company"
    role = form.get("role", "Software Engineer Intern").strip() or "Software Engineer Intern"
    skills = form.get("skills", "Python, SQL, full-stack development").strip() or "Python, SQL, full-stack development"
    achievement = form.get("achievement", "built projects that improved user experience and solved real problems").strip()
    tone = form.get("tone", "Professional")
    opener = {
        "Formal": "I am writing to apply for",
        "Friendly": "I am excited to apply for",
        "Enthusiastic": "I am thrilled to apply for",
    }.get(tone, "I am writing to express my interest in")
    return (
        f"Dear Hiring Manager,\n\n"
        f"{opener} the {role} position at {company}. My background in {skills} aligns well with the responsibilities of this role, and I am eager to contribute to meaningful engineering work.\n\n"
        f"In my recent work, I {achievement}. This experience strengthened my ability to understand requirements, build reliable solutions, and communicate progress clearly with a team.\n\n"
        f"What interests me most about {company} is the opportunity to solve practical problems at a high standard. I would welcome the chance to discuss how my skills and project experience can support your team.\n\n"
        f"Warm regards,\n{name}"
    )


@app.context_processor
def inject_layout_data():
    return {"nav_items": NAV_ITEMS, "current_year": date.today().year}


@app.route("/")
def dashboard():
    applications = get_applications()
    jobs = get_jobs()
    upcoming = [app for app in applications if app["status"] in {"Interview Scheduled", "Technical Round", "HR Round"}][:3]
    suggestions = [
        "Add missing skills from your highest-match jobs to your resume.",
        "Move active interview applications to the right tracker stage.",
        "Generate a tailored cover letter before applying to recommended roles.",
    ]
    return render_template(
        "dashboard.html",
        title="Dashboard",
        stats=build_dashboard_stats(applications),
        applications=applications[:5],
        jobs=jobs[:3],
        upcoming=upcoming,
        suggestions=suggestions,
    )


@app.route("/resume", methods=["GET", "POST"])
def resume():
    analysis = None
    resume_text = ""
    job_description = ""
    if request.method == "POST":
        uploaded_text, filename, extraction_note = extract_text_from_upload(request.files.get("resume"))
        resume_text = request.form.get("resume_text", "")
        job_description = request.form.get("job_description", "")
        analysis = analyze_resume_text(f"{uploaded_text}\n{resume_text}", job_description, filename, extraction_note)
    return render_template("resume.html", title="Resume Analyzer", analysis=analysis, resume_text=resume_text, job_description=job_description)


@app.route("/jobs")
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
def apply_to_job(job_id: int):
    with get_db() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if job:
            conn.execute(
                """
                INSERT INTO applications (company, role, status, applied_on, notes, match_score)
                VALUES (?, ?, 'Applied', ?, 'Added from Job Matcher', ?)
                """,
                (job["company"], job["title"], date.today().isoformat(), job["match_score"]),
            )
    return redirect(url_for("tracker"))


@app.route("/cover-letter", methods=["GET", "POST"])
def cover_letter():
    letter = None
    if request.method == "POST":
        letter = make_cover_letter(request.form)
    return render_template("cover_letter.html", title="Cover Letter", generated=letter is not None, letter=letter, form=request.form)


@app.route("/interview")
def interview():
    category = request.args.get("category", "Technical")
    if category not in INTERVIEW_QUESTIONS:
        category = "Technical"
    return render_template("interview.html", title="Interview Prep", category=category, questions=INTERVIEW_QUESTIONS)


@app.route("/tracker")
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
def add_application():
    company = request.form.get("company", "").strip()
    role = request.form.get("role", "").strip()
    if company and role:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO applications (company, role, status, applied_on, notes, match_score)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
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
def update_application_status(application_id: int):
    payload = request.get_json(silent=True) or request.form
    status = payload.get("status", "Applied")
    if status not in STATUSES:
        return jsonify({"ok": False, "error": "Invalid status"}), 400
    with get_db() as conn:
        conn.execute("UPDATE applications SET status = ? WHERE id = ?", (status, application_id))
    return jsonify({"ok": True})


@app.post("/applications/<int:application_id>/delete")
def delete_application(application_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM applications WHERE id = ?", (application_id,))
    return redirect(url_for("tracker"))


@app.route("/profile")
def profile():
    return render_template("simple_page.html", title="Profile", heading="Profile", description="Manage your profile, resume links, portfolio, and preferred roles.")


@app.route("/settings")
def settings():
    return render_template("simple_page.html", title="Settings", heading="Settings", description="Configure notifications, privacy preferences, appearance, and AI defaults.")


@app.route("/admin")
def admin():
    applications = get_applications()
    by_status = defaultdict(int)
    for application in applications:
        by_status[application["status"]] += 1
    description = f"SQLite database is active with {len(applications)} applications. Status counts: " + ", ".join(f"{status}: {by_status[status]}" for status in STATUSES)
    return render_template("simple_page.html", title="Admin", heading="Admin", description=description)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        return redirect(url_for("dashboard"))
    return render_template("login.html", title="Login")


init_db()


if __name__ == "__main__":
    app.run(debug=True)
