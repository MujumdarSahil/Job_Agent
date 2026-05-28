# scrapers/jobspy_scraper.py
from jobspy import scrape_jobs
import pandas as pd

INDIA_CITIES = {
    "mumbai": "Mumbai, Maharashtra, India",
    "delhi": "Delhi, India",
    "noida": "Noida, Uttar Pradesh, India",
    "gurgaon": "Gurugram, Haryana, India",
    "gurugram": "Gurugram, Haryana, India",
    "bangalore": "Bengaluru, Karnataka, India",
    "bengaluru": "Bengaluru, Karnataka, India",
    "hyderabad": "Hyderabad, Telangana, India",
    "pune": "Pune, Maharashtra, India",
    "chennai": "Chennai, Tamil Nadu, India",
    "kolkata": "Kolkata, West Bengal, India",
    "ahmedabad": "Ahmedabad, Gujarat, India",
}


def normalize_location(location: str) -> tuple[str, bool]:
    """Return (JobSpy location string, whether user also wants remote jobs)."""
    raw = location.strip()
    lower = raw.lower()
    wants_remote = "remote" in lower

    city_part = lower
    for sep in (" or remote", "/remote", ", remote", " & remote"):
        city_part = city_part.replace(sep, "")
    city_part = city_part.replace("remote", "").strip(" ,")

    if not city_part or city_part == "remote":
        return "India", True

    for key, full in INDIA_CITIES.items():
        if key in city_part:
            return full, wants_remote

    if "india" in city_part:
        return raw.split(" or ")[0].split("/")[0].strip(), wants_remote

    city = city_part.split(",")[0].strip().title()
    return f"{city}, India", wants_remote


def _scrape(search_term: str, location: str, is_remote: bool = False, results: int = 20) -> list[dict]:
    jobs = scrape_jobs(
        site_name=["linkedin", "indeed"],
        search_term=search_term,
        location=location,
        is_remote=is_remote,
        results_wanted=results,
        hours_old=168,
        country_indeed="India",
    )
    if jobs is None or jobs.empty:
        return []
    return jobs.fillna("").to_dict(orient="records")


def scrape_all_boards(
    search_term: str,
    location: str,
    results_per_site: int = 20,
    remote_preference: str = "any",
) -> list[dict]:
    clean_loc, wants_remote = normalize_location(location)
    include_remote = wants_remote or remote_preference in ("yes", "any")

    all_jobs: list[dict] = []
    all_jobs.extend(_scrape(search_term, clean_loc, is_remote=False, results=results_per_site))

    if include_remote:
        all_jobs.extend(_scrape(search_term, clean_loc, is_remote=True, results=results_per_site))

    return all_jobs
