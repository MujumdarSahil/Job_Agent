# main.py
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, IntPrompt
from rich.progress import Progress

from resume_parser import parse_resume, resolve_resume_path
from agent import extract_profile, score_job
from scrapers.jobspy_scraper import scrape_all_boards
from scrapers.remoteok_scraper import scrape_remoteok
from scorer import filter_by_experience
from applier import (
    linkedin_easy_apply,
    run_email_apply,
    run_packet_apply,
)
from config import GMAIL_USER, GMAIL_APP_PASSWORD

console = Console()


def gather_preferences() -> dict:
    console.rule("[bold]AI Job Agent[/bold]")
    return {
        "role": Prompt.ask("Job title / role you're looking for"),
        "location": Prompt.ask("Location (e.g. Mumbai, Mumbai or remote, Remote)"),
        "min_salary": IntPrompt.ask("Minimum salary (INR/year)", default=0),
        "job_type": Prompt.ask("Job type", choices=["fulltime", "parttime", "contract", "any"], default="fulltime"),
        "remote": Prompt.ask("Remote preference", choices=["yes", "no", "hybrid", "any"], default="any"),
        "experience": Prompt.ask("Experience level", choices=["junior", "mid", "senior", "any"], default="any"),
    }


def display_results(scored_jobs: list[dict]):
    table = Table(title="Top Job Matches", show_lines=True)
    table.add_column("Score", style="bold green", width=7)
    table.add_column("Title", style="bold", width=28)
    table.add_column("Company", width=20)
    table.add_column("Location", width=18)
    table.add_column("Reason", width=40)
    table.add_column("Apply", width=6)

    for job in scored_jobs[:15]:
        score = job.get("score", 0)
        color = "green" if score >= 8 else "yellow" if score >= 6 else "red"
        table.add_row(
            f"[{color}]{score}/10[/{color}]",
            job.get("title", "")[:27],
            job.get("company", "")[:19],
            job.get("location", "")[:17],
            job.get("reason", "")[:39],
            "✅" if job.get("apply") else "❌",
        )
    console.print(table)


def export_results(jobs: list[dict], filename="results"):
    import pandas as pd

    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = results_dir / f"{filename}_{ts}.xlsx"

    columns = ["score", "title", "company", "location", "job_url", "reason", "apply"]
    df = pd.DataFrame([{k: j.get(k, "") for k in columns} for j in jobs], columns=columns)
    df.to_excel(out_path, index=False, sheet_name="results")
    console.print(f"[green]Saved to {out_path}[/green]")


def handle_apply(scored: list[dict], profile: dict, resume: dict, resume_pdf_path):
    applyable = [j for j in scored if j.get("apply") and j.get("score", 0) >= 8]
    console.print(
        f"\n[dim]{len(applyable)} jobs marked ✅ with score ≥ 8 (eligible for apply flows)[/dim]"
    )
    console.print(
        "[yellow]Note: Full auto-apply on LinkedIn/Indeed/Naukri is not possible for every site. "
        "Email works when a listing has a contact email; LinkedIn only supports Easy Apply jobs.[/yellow]"
    )

    apply_choice = Prompt.ask(
        "\nHow would you like to apply?",
        choices=["linkedin", "email", "packet", "skip"],
        default="skip",
    )

    if apply_choice == "skip":
        return

    if apply_choice == "linkedin":
        profile["phone"] = profile.get("phone") or Prompt.ask("Your phone number")
        profile["experience_years"] = resume.get("experience_years", 1)
        linkedin_easy_apply(scored, profile)

    elif apply_choice == "email":
        sender = GMAIL_USER or Prompt.ask("Your Gmail address")
        app_pw = GMAIL_APP_PASSWORD or Prompt.ask(
            "Gmail App Password (16 chars — NOT your normal password)", password=True
        )
        console.print("[dim]Create App Password: https://myaccount.google.com/apppasswords[/dim]")
        try:
            sent = run_email_apply(scored, profile, resume["raw_text"], resume_pdf_path, sender, app_pw)
            console.print(f"[green]Sent {sent} application email(s)[/green]")
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")

    elif apply_choice == "packet":
        count = run_packet_apply(scored, profile, resume["raw_text"])
        console.print(f"[green]Generated {count} apply packet(s) — fill forms in the opened browser tabs[/green]")


def main():
    resume_path, note = resolve_resume_path(
        Prompt.ask("Path to your resume PDF (file or resume folder)")
    )
    if note:
        console.print(f"[dim]{note}[/dim]")
    resume = parse_resume(resume_path)
    console.print(f"[green]✓ Resume parsed — found {len(resume['skills'])} skills[/green]")

    prefs = gather_preferences()

    with console.status("AI analyzing your resume..."):
        profile = extract_profile(resume, prefs)
    profile["target_experience"] = prefs["experience"]
    profile["experience_years"] = resume.get("experience_years", 1)
    console.print(f"[green]✓ Profile built — targeting: {', '.join(profile['job_titles'][:3])}[/green]")

    all_jobs = []
    with Progress() as progress:
        task = progress.add_task("Scraping jobs...", total=4)

        for title in profile["job_titles"][:2]:
            jobs = scrape_all_boards(title, prefs["location"], remote_preference=prefs["remote"])
            all_jobs.extend(jobs)
            progress.advance(task)

        all_jobs.extend(scrape_remoteok(prefs["role"]))
        progress.advance(task, 2)

    seen = set()
    unique_jobs = []
    for job in all_jobs:
        key = f"{job.get('title', '').lower()}|{job.get('company', '').lower()}"
        if key not in seen:
            seen.add(key)
            unique_jobs.append(job)

    console.print(f"[green]✓ Found {len(unique_jobs)} unique jobs[/green]")

    if prefs["experience"] != "any":
        before = len(unique_jobs)
        unique_jobs = filter_by_experience(unique_jobs, prefs["experience"])
        console.print(
            f"[dim]Experience filter ({prefs['experience']}): removed {before - len(unique_jobs)}, "
            f"{len(unique_jobs)} remaining[/dim]"
        )

    scored = []
    with Progress() as progress:
        task = progress.add_task("AI scoring jobs...", total=len(unique_jobs[:30]))
        for job in unique_jobs[:30]:
            try:
                scored.append(score_job(job, profile))
            except Exception:
                scored.append({**job, "score": 0, "reason": "Could not score", "apply": False})
            progress.advance(task)

    scored.sort(key=lambda x: x.get("score", 0), reverse=True)

    display_results(scored)

    if Prompt.ask("Export to Excel?", choices=["yes", "no"], default="yes") == "yes":
        export_results(scored)

    handle_apply(scored, profile, resume, resume_path)


if __name__ == "__main__":
    main()
