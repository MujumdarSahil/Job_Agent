# scrapers/remoteok_scraper.py
import requests

def scrape_remoteok(search_term: str, limit: int = 20) -> list[dict]:
    """Free public API — filter by search keywords (tag endpoint often returns 0)."""
    url = "https://remoteok.com/api"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; JobAgent/1.0)"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    raw = resp.json()
    jobs = [j for j in raw if isinstance(j, dict) and j.get("position")]

    terms = [t for t in search_term.lower().replace("-", " ").split() if len(t) > 2]
    if terms:
        matched = []
        for j in jobs:
            haystack = " ".join(
                [
                    j.get("position", ""),
                    j.get("company", ""),
                    " ".join(j.get("tags") or []) if isinstance(j.get("tags"), list) else str(j.get("tags", "")),
                ]
            ).lower()
            if any(t in haystack for t in terms):
                matched.append(j)
        jobs = matched or jobs

    return [
        {
            "title": j.get("position", ""),
            "company": j.get("company", ""),
            "location": "Remote",
            "job_url": f"https://remoteok.com/l/{j.get('slug', '')}",
            "description": j.get("description", ""),
            "date_posted": j.get("date", ""),
        }
        for j in jobs[:limit]
    ]
