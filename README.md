# CareerAI - Job Internship Application Tracker

CareerAI is a Flask + SQLite job application assistant with Gemini-powered resume analysis, AI cover letters, authentication, profile/settings management, and a drag-and-drop application tracker.

## Features

- Gemini 2.5 Flash resume analysis with ATS score, keyword score, matched skills, missing skills, strengths, suggestions, and summary
- PDF, DOCX, and TXT resume extraction with pypdf first and pdfplumber fallback for PDFs
- AJAX resume analyzer with progress steps and saved analysis history
- Gemini-powered three-paragraph cover letter generator with copy and regenerate controls
- Dashboard with saved application stats and animated counters
- Sortable.js Kanban tracker with persisted status updates
- Single-user Flask-Login authentication using an `APP_PASSWORD` hash
- Profile and settings pages persisted in SQLite
- SQLite database stored at `instance/careerai.db`

## Project Structure

```text
.
|-- app.py
|-- ai.py
|-- db.py
|-- requirements.txt
|-- .env.example
|-- static/
|   |-- css/style.css
|   `-- js/app.js
|-- templates/
|   |-- base.html
|   |-- dashboard.html
|   |-- resume.html
|   |-- jobs.html
|   |-- cover_letter.html
|   |-- interview.html
|   |-- tracker.html
|   |-- profile.html
|   |-- settings.html
|   |-- simple_page.html
|   `-- login.html
`-- instance/
    `-- careerai.db
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Set `GEMINI_API_KEY` in `.env` or save it from the Settings page. Set `APP_PASSWORD` to a Werkzeug password hash. For local development only, the fallback password is `careerai`.

Open `http://127.0.0.1:5000` in your browser.

## Deploying on Vercel

Vercel can detect the Flask `app` object in `app.py` from `requirements.txt`. Add these environment variables in the Vercel project settings:

- `SECRET_KEY`: any long random string
- `APP_PASSWORD`: a Werkzeug password hash for your login password
- `GEMINI_API_KEY`: optional at startup, required for AI resume/job/cover-letter features

On Vercel, SQLite data and uploads are stored in `/tmp` so the serverless function can start. That storage is temporary, so use a hosted database such as Postgres/Supabase if you need saved applications and resumes to persist across deployments or function restarts.
