from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from db import get_setting

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - handled at runtime
    genai = None

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional fallback
    OpenAI = None


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

LOGGER = logging.getLogger(__name__)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

RESUME_SCHEMA = {
    "resume_score": 0,
    "ats_score": 0,
    "strengths": [],
    "weaknesses": [],
    "missing_skills": [],
    "suggestions": [],
    "recommended_roles": [],
}

JOB_MATCH_SCHEMA = {
    "match_score": 0,
    "matched_skills": [],
    "missing_skills": [],
    "improvement_suggestions": [],
}


class AIError(RuntimeError):
    pass


def get_gemini_api_key() -> str:
    load_dotenv(ENV_PATH, override=False)
    return (get_setting("gemini_api_key") or os.getenv("GEMINI_API_KEY") or "").strip()


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
        "resume_score": _clamp_score(analysis.get("resume_score")),
        "ats_score": _clamp_score(analysis.get("ats_score")),
        "strengths": _as_list(analysis.get("strengths")),
        "weaknesses": _as_list(analysis.get("weaknesses")),
        "missing_skills": _as_list(analysis.get("missing_skills")),
        "suggestions": _as_list(analysis.get("suggestions")),
        "recommended_roles": _as_list(analysis.get("recommended_roles")),
    }


def validate_job_match(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = JOB_MATCH_SCHEMA | payload
    return {
        "match_score": _clamp_score(analysis.get("match_score")),
        "matched_skills": _as_list(analysis.get("matched_skills")),
        "missing_skills": _as_list(analysis.get("missing_skills")),
        "improvement_suggestions": _as_list(analysis.get("improvement_suggestions")),
    }


def _generate_json(prompt: str) -> dict[str, Any]:
    gemini_key = get_gemini_api_key()
    if gemini_key and genai is not None:
        genai.configure(api_key=gemini_key)
        response = genai.GenerativeModel(GEMINI_MODEL).generate_content(
            prompt,
            generation_config={"temperature": 0.2, "response_mime_type": "application/json"},
        )
        return _extract_json(response.text or "")

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key and OpenAI is not None:
        client = OpenAI(api_key=openai_key)
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=prompt,
            temperature=0.2,
        )
        return _extract_json(response.output_text or "")

    raise AIError("Add a Gemini API key in Settings or GEMINI_API_KEY/OPENAI_API_KEY in .env before running AI analysis.")


def analyze_resume(resume_text: str) -> dict[str, Any]:
    prompt = f"""
Analyze the following resume and return JSON only.

{{
"resume_score": 0-100,
"ats_score": 0-100,
"strengths": [],
"weaknesses": [],
"missing_skills": [],
"suggestions": [],
"recommended_roles": []
}}

Resume:
{resume_text[:24000]}
"""
    try:
        return validate_resume_analysis(_generate_json(prompt))
    except Exception as exc:
        LOGGER.exception("Resume analysis failed")
        raise AIError(str(exc)) from exc


def match_job_description(resume_text: str, job_description: str) -> dict[str, Any]:
    prompt = f"""
Compare the candidate resume against the job description. Consider resume skills, experience, and education against job requirements.
Return JSON only with exactly these keys:
{json.dumps(JOB_MATCH_SCHEMA)}

Rules:
- match_score must be an integer from 0 to 100.
- matched_skills and missing_skills must be concise skill names.
- improvement_suggestions must be specific actions the candidate can take.
- Do not invent experience or education.

Resume:
{resume_text[:18000]}

Job Description:
{job_description[:12000]}
"""
    try:
        return validate_job_match(_generate_json(prompt))
    except Exception as exc:
        LOGGER.exception("Job match analysis failed")
        raise AIError(str(exc)) from exc


def generate_cover_letter_with_gemini(form: dict[str, str]) -> tuple[str | None, str | None]:
    name = form.get("name", "").strip()
    company = form.get("company", "").strip()
    role = form.get("role", "").strip()
    skills = form.get("skills", "").strip()
    achievement = form.get("achievement", "").strip()
    tone = form.get("tone", "Professional").strip() or "Professional"
    if not all([name, company, role, skills, achievement]):
        return None, "Complete all cover letter fields before generating."

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
        response = _generate_json(
            "Return JSON only in this shape: {\"letter\":\"...\"}\n\n" + prompt
        )
        letter = str(response.get("letter") or "").strip()
        if not letter:
            raise AIError("The AI returned an empty cover letter.")
        return letter, None
    except Exception as exc:
        LOGGER.exception("Cover letter generation failed")
        return None, str(exc)
