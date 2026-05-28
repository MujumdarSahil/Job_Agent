# agent.py
from groq import Groq
import json
import re

from config import GROQ_API_KEY

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

MODEL = "llama-3.3-70b-versatile"


def parse_json_response(text: str) -> dict:
    """Parse JSON from model output (handles fences and extra prose)."""
    if not text or not text.strip():
        raise ValueError("Empty response from model")

    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fenced:
        return json.loads(fenced.group(1).strip())

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError(f"Could not parse JSON from model response: {text[:300]!r}")


def _chat_json(prompt: str, temperature: float = 0.2) -> dict:
    if not client:
        raise RuntimeError(
            "GROQ_API_KEY is not configured. Add it in your .env file."
        )
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You must respond with valid JSON only. No markdown."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    return parse_json_response(content or "")


def extract_profile(resume: dict, preferences: dict) -> dict:
    """AI extracts a clean job-search profile from resume + preferences."""
    prefs = {**preferences, "min_salary_note": "INR per year"}
    prompt = f"""Analyze this resume and return a JSON object with exactly these keys:
- top_skills: array of 10 strings
- job_titles: array of 5 strings (job titles to search for)
- seniority: one of "junior", "mid", "senior"
- summary: string (2-sentence professional summary)

Resume text:
{resume['raw_text'][:3000]}

User preferences:
{json.dumps(prefs)}
"""
    return _chat_json(prompt, temperature=0.3)


def score_job(job: dict, profile: dict) -> dict:
    """AI scores a job listing against the candidate profile (1-10)."""
    target_exp = profile.get("target_experience", "any")
    prompt = f"""Score this job 1-10 for this candidate. Return JSON with keys:
- score: integer 1-10
- reason: string (one short sentence)
- apply: boolean

Rules:
- Target experience level: {target_exp}
- If target is "junior", set apply=false for senior/lead/principal roles (5+ years required, "Sr." in title, etc.)
- If target is "senior", set apply=false for junior/entry-level/intern roles
- Penalize score heavily when seniority clearly does not match target level

Candidate profile:
{json.dumps(profile)}

Job:
Title={job.get('title')}
Company={job.get('company')}
Location={job.get('location')}
Description={str(job.get('description', ''))[:800]}
"""
    result = _chat_json(prompt, temperature=0.1)

    if profile.get("target_experience") == "junior":
        from scorer import is_senior_job
        if is_senior_job(job):
            result["apply"] = False
            result["score"] = min(result.get("score", 0), 4)
            result["reason"] = "Senior-level role — filtered for junior preference"

    return {**job, **result}
