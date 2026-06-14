from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv

from db import get_setting

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - handled at runtime for graceful setup
    genai = None


load_dotenv()

MODEL_NAME = "gemini-2.5-flash"

RESUME_SCHEMA = {
    "score": 0,
    "ats_score": 0,
    "keyword_score": 0,
    "matched_skills": [],
    "missing_skills": [],
    "strengths": [],
    "suggestions": [],
    "summary": "",
}


class AIError(RuntimeError):
    pass


def get_gemini_api_key() -> str:
    return (get_setting("gemini_api_key") or os.getenv("GEMINI_API_KEY") or "").strip()


def _model():
    api_key = get_gemini_api_key()
    if not api_key:
        raise AIError("Gemini API key is missing. Add GEMINI_API_KEY in .env or save it in Settings.")
    if genai is None:
        raise AIError("google-generativeai is not installed. Run pip install -r requirements.txt.")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(MODEL_NAME)


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _clamp_score(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def validate_resume_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = RESUME_SCHEMA | payload
    return {
        "score": _clamp_score(analysis.get("score")),
        "ats_score": _clamp_score(analysis.get("ats_score")),
        "keyword_score": _clamp_score(analysis.get("keyword_score")),
        "matched_skills": _as_list(analysis.get("matched_skills")),
        "missing_skills": _as_list(analysis.get("missing_skills")),
        "strengths": _as_list(analysis.get("strengths")),
        "suggestions": _as_list(analysis.get("suggestions")),
        "summary": str(analysis.get("summary") or "").strip(),
    }


def fallback_resume_analysis(resume_text: str, job_description: str, message: str) -> dict[str, Any]:
    resume_lower = resume_text.lower()
    job_lower = job_description.lower()
    skills = [
        "python", "flask", "sql", "sqlite", "javascript", "react", "api", "git",
        "machine learning", "data analysis", "communication", "leadership",
    ]
    required = [skill for skill in skills if skill in job_lower] or skills[:6]
    matched = [skill.title() for skill in required if skill in resume_lower]
    missing = [skill.title() for skill in required if skill.title() not in matched]
    keyword_score = round((len(matched) / max(1, len(required))) * 100)
    score = max(35, min(82, keyword_score + 12))
    return {
        "score": score,
        "ats_score": max(40, min(85, score + 5)),
        "keyword_score": keyword_score,
        "matched_skills": matched,
        "missing_skills": missing or ["Add more role-specific proof points"],
        "strengths": [
            "Resume and job description were received successfully.",
            "Fallback analysis found keyword overlap while AI was unavailable.",
        ],
        "suggestions": [
            "Add measurable outcomes to projects and work experience.",
            "Mirror the most important job description keywords where they are truthful.",
            "Use clear headings for Skills, Projects, Experience, and Education.",
        ],
        "summary": f"AI analysis could not be completed: {message}",
        "fallback": True,
    }


def analyze_resume_with_gemini(resume_text: str, job_description: str) -> dict[str, Any]:
    prompt = f"""
You are an expert ATS resume reviewer and technical recruiter. Analyze the resume and job description.
Return only valid JSON with exactly these keys:
{json.dumps(RESUME_SCHEMA)}

Rules:
- score, ats_score, and keyword_score must be integers from 0 to 100.
- matched_skills and missing_skills must be concise skill names.
- strengths and suggestions must be practical bullet-style strings.
- summary must be one concise professional paragraph.
- Do not invent experience; base feedback on the supplied text.

Resume:
{resume_text[:18000]}

Job Description:
{job_description[:12000]}
"""
    try:
        response = _model().generate_content(
            prompt,
            generation_config={
                "temperature": 0.25,
                "response_mime_type": "application/json",
            },
        )
        payload = _extract_json(response.text or "")
        return validate_resume_analysis(payload)
    except Exception as exc:
        return fallback_resume_analysis(resume_text, job_description, str(exc))


def generate_cover_letter_with_gemini(form: dict[str, str]) -> tuple[str, str | None]:
    name = form.get("name", "").strip() or "Applicant"
    company = form.get("company", "").strip() or "the company"
    role = form.get("role", "").strip() or "the role"
    skills = form.get("skills", "").strip() or "relevant technical skills"
    achievement = form.get("achievement", "").strip() or "built practical projects and collaborated with teams"
    tone = form.get("tone", "Professional").strip() or "Professional"
    prompt = f"""
Write a natural, human-sounding cover letter with exactly three paragraphs.
Personalize it for:
- Full Name: {name}
- Company: {company}
- Role: {role}
- Skills: {skills}
- Achievement: {achievement}
- Tone: {tone}

Requirements:
- Professional and concise.
- No bullet points.
- Do not include placeholders.
- End with the applicant's name.
"""
    try:
        response = _model().generate_content(prompt, generation_config={"temperature": 0.65})
        letter = (response.text or "").strip()
        if not letter:
            raise AIError("Gemini returned an empty cover letter.")
        return letter, None
    except Exception as exc:
        fallback = (
            f"Dear Hiring Manager,\n\n"
            f"I am excited to apply for the {role} position at {company}. My experience with {skills} has helped me build practical, reliable solutions, and I am eager to bring that same focus to your team.\n\n"
            f"One achievement I am proud of is that I {achievement}. This strengthened my ability to connect technical work with measurable outcomes while communicating clearly and adapting quickly.\n\n"
            f"I would welcome the opportunity to discuss how my background can support {company}'s goals. Thank you for your time and consideration.\n\n"
            f"Sincerely,\n{name}"
        )
        return fallback, str(exc)

