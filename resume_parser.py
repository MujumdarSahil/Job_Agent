# resume_parser.py
import pdfplumber
import re
from pathlib import Path


def resolve_resume_path(path: str) -> tuple[Path, str | None]:
    """Resolve a PDF file path. If *path* is a folder, pick the newest PDF inside."""
    cleaned = path.strip().strip('"').strip("'")
    p = Path(cleaned).expanduser().resolve()

    if not p.exists():
        raise FileNotFoundError(f"Path not found: {cleaned}")

    if p.is_dir():
        pdfs = sorted(p.glob("*.pdf"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not pdfs:
            raise FileNotFoundError(f"No PDF files found in folder: {p}")
        chosen = pdfs[0]
        note = f"Using resume: {chosen.name}"
        if len(pdfs) > 1:
            note += f" ({len(pdfs)} PDFs in folder; picked most recent)"
        return chosen, note

    if p.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {p.name}")

    return p, None


def parse_resume(pdf_path: str | Path) -> dict:
    path = pdf_path if isinstance(pdf_path, Path) else resolve_resume_path(pdf_path)[0]
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""

    return {
        "raw_text": text,
        "skills": extract_skills(text),
        "experience_years": estimate_experience(text),
    }

def extract_skills(text: str) -> list[str]:
    # Common tech skills — extend this list
    SKILLS = [
        "Python","JavaScript","TypeScript","React","Node.js","SQL","AWS","Docker",
        "Kubernetes","FastAPI","Django","PostgreSQL","MongoDB","Redis","Git",
        "Machine Learning","TensorFlow","PyTorch","REST API","GraphQL","Java","Go",
    ]
    found = [s for s in SKILLS if s.lower() in text.lower()]
    return found

def estimate_experience(text: str) -> int:
    years = re.findall(r'(\d+)\+?\s+years?', text, re.IGNORECASE)
    return max((int(y) for y in years), default=0)