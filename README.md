# CareerAI - Job Internship Application Tracker

CareerAI is a Flask-based AI + Python project for students managing internship and job applications. It now uses SQLite so application data is saved after refreshes and restarts.

## Features

- Dashboard with live stats from saved applications
- Resume Analyzer with PDF/TXT upload, keyword-based ATS scoring, and skill-gap feedback
- Job Matcher with search, filters, and Apply buttons
- Cover Letter Generator that creates a draft from your inputs
- Interview Prep question bank by category
- Application Tracker with saved add/delete/status updates
- SQLite database stored at `instance/careerai.db`

## Project Structure

```text
.
|-- app.py
|-- requirements.txt
|-- .env.example
|-- static/
|   |-- css/
|   |   `-- style.css
|   |-- js/
|   |   `-- app.js
|   `-- uploads/
|-- templates/
|   |-- base.html
|   |-- dashboard.html
|   |-- resume.html
|   |-- jobs.html
|   |-- cover_letter.html
|   |-- interview.html
|   |-- tracker.html
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
python app.py
```

Open `http://127.0.0.1:5000` in your browser.

## Notes

The current AI features are local rule-based features, so they work without an API key. The resume analyzer reads selectable-text PDFs with `pypdf`. You can later connect OpenAI or another model API inside `analyze_resume_text()` and `make_cover_letter()` in `app.py`.
