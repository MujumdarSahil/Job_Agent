# scorer.py
import re

# Strong signals in job title
SENIOR_TITLE_PATTERNS = [
    r"\bsr\.?\b",
    r"\bsenior\b",
    r"\blead\b",
    r"\bprincipal\b",
    r"\barchitect\b",
    r"\bdirector\b",
    r"\bhead of\b",
    r"\bvp\b",
    r"\bvice president\b",
    r"\bchief\b",
    r"\bstaff engineer\b",
    r"\bengineering manager\b",
    r"\bmanager\b",
    r"\bexpert\b",
    r"\biii\b",
    r"\bii\b",
    r"\blevel\s*[3-9]\b",
    r"\b[2-9]-[1-9]\b",  # e.g. Role 2-1
]

JUNIOR_TITLE_PATTERNS = [
    r"\bjunior\b",
    r"\bjr\.?\b",
    r"\bentry[\s-]?level\b",
    r"\bgraduate\b",
    r"\bfresher\b",
    r"\btrainee\b",
    r"\bintern\b",
    r"\bassociate\b",
]

SENIOR_DESC_PATTERNS = [
    r"\b(10|8|7|6|5)\+?\s*years?\s+(of\s+)?experience\b",
    r"\bminimum\s+(of\s+)?[5-9]\+?\s*years?\b",
    r"\bsenior level\b",
]


def _job_title(job: dict) -> str:
    return (job.get("title") or "").lower()


def _job_text(job: dict) -> str:
    return f"{job.get('title', '')} {job.get('description', '')}".lower()


def is_senior_job(job: dict) -> bool:
    title = _job_title(job)
    for pattern in SENIOR_TITLE_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return True

    text = _job_text(job)
    for pattern in SENIOR_DESC_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def is_junior_job(job: dict) -> bool:
    title = _job_title(job)
    return any(re.search(p, title, re.IGNORECASE) for p in JUNIOR_TITLE_PATTERNS)


def matches_experience_level(job: dict, level: str) -> bool:
    if level == "any":
        return True

    senior = is_senior_job(job)
    junior = is_junior_job(job)

    if level == "junior":
        return not senior

    if level == "senior":
        return senior or not junior

    if level == "mid":
        return not senior and not junior

    return True


def filter_by_experience(jobs: list[dict], level: str) -> list[dict]:
    if level == "any":
        return jobs
    return [j for j in jobs if matches_experience_level(j, level)]
