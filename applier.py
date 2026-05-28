# applier.py
import json
import re
import smtplib
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from agent import client, parse_json_response, MODEL
from config import GMAIL_USER, GMAIL_APP_PASSWORD

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.IGNORECASE)


def _require_groq():
    if not client:
        raise RuntimeError("Groq client not configured in agent.py")


def _validate_gmail_login(sender_email: str, sender_password: str):
    """Fail fast with a clear message when Gmail auth is invalid."""
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password.replace(" ", ""))
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(
            "Gmail authentication failed (535 BadCredentials).\n"
            "Use a Google App Password (16 chars), not your regular Gmail password.\n"
            "Steps:\n"
            "1) Enable 2-Step Verification on your Google account.\n"
            "2) Create an App Password at https://myaccount.google.com/apppasswords\n"
            "3) Set GMAIL_USER and GMAIL_APP_PASSWORD in .env and run again."
        ) from e


def get_applyable_jobs(jobs: list[dict], min_score: int = 8) -> list[dict]:
    """Jobs the agent marked as worth applying to."""
    return [
        j for j in jobs
        if j.get("apply") and j.get("score", 0) >= min_score
    ]


def find_contact_emails(job: dict) -> list[str]:
    """Collect recruiter emails from JobSpy field or description text."""
    found: list[str] = []
    raw_emails = job.get("emails")
    if raw_emails:
        if isinstance(raw_emails, str):
            found.extend(EMAIL_RE.findall(raw_emails))
        elif isinstance(raw_emails, list):
            found.extend(str(e) for e in raw_emails if e)

    desc = job.get("description") or ""
    found.extend(EMAIL_RE.findall(desc))
    # Dedupe, skip noreply
    seen = set()
    clean = []
    for e in found:
        el = e.lower()
        if el in seen or "noreply" in el or "no-reply" in el:
            continue
        seen.add(el)
        clean.append(e)
    return clean


def generate_cover_letter(job: dict, profile: dict, resume_text: str) -> str:
    _require_groq()
    prompt = f"""
Write a concise, professional cover letter (150-200 words) for this job.

Candidate profile: {json.dumps(profile)}
Resume summary: {resume_text[:1500]}

Job: {job.get('title')} at {job.get('company')}
Description: {str(job.get('description', ''))[:600]}

Rules:
- Sound human and enthusiastic, NOT generic
- Mention 2-3 specific skills that match THIS job
- End with a call to action
- Start with "Hello {job.get('company', 'Team')} Team,"
- Return ONLY the letter text
"""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return (resp.choices[0].message.content or "").strip()


def send_email_application(
    job: dict,
    profile: dict,
    resume_text: str,
    resume_pdf_path: str | Path,
    sender_email: str,
    sender_password: str,
    to_email: str,
) -> str:
    cover_letter = generate_cover_letter(job, profile, resume_text)
    pdf_path = Path(resume_pdf_path)

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = f"Application — {job.get('title', 'Role')} | {profile.get('name', 'Candidate')}"
    msg.attach(MIMEText(cover_letter, "plain"))

    with open(pdf_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{pdf_path.name}"')
    msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, sender_password.replace(" ", ""))
        server.sendmail(sender_email, to_email, msg.as_string())

    print(f"Email sent to {to_email} for {job.get('title')} @ {job.get('company')}")
    return cover_letter


def run_email_apply(
    jobs: list[dict],
    profile: dict,
    resume_text: str,
    resume_pdf_path: str | Path,
    sender_email: str | None = None,
    sender_password: str | None = None,
    limit: int = 10,
) -> int:
    sender = sender_email or GMAIL_USER
    password = sender_password or GMAIL_APP_PASSWORD
    if not sender or not password:
        raise RuntimeError(
            "Set GMAIL_USER and GMAIL_APP_PASSWORD in .env, or enter them when prompted."
        )

    _validate_gmail_login(sender, password)

    targets = get_applyable_jobs(jobs)
    sent = 0
    for job in targets[:limit]:
        emails = find_contact_emails(job)
        if not emails:
            print(f"Skip (no email in listing): {job.get('title')} @ {job.get('company')}")
            continue
        to_email = emails[0]
        print(f"Sending to {to_email} — {job.get('title')} @ {job.get('company')}...")
        send_email_application(job, profile, resume_text, resume_pdf_path, sender, password, to_email)
        sent += 1
    return sent


def linkedin_easy_apply(
    jobs: list[dict],
    profile: dict,
):
    """
    Semi-automated LinkedIn Easy Apply.
    LinkedIn often blocks bots — expect CAPTCHA/2FA and manual review on some forms.
    Only works for linkedin.com URLs with an Easy Apply button.
    """
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options)
    wait = WebDriverWait(driver, 15)

    driver.get("https://www.linkedin.com/login")
    time.sleep(2)
    print("Please log in to LinkedIn manually in the opened browser window.")
    print("Complete any 2FA/CAPTCHA prompts, then return here.")
    input("Press Enter once you are fully logged in...")

    applied_count = 0
    targets = [j for j in get_applyable_jobs(jobs) if "linkedin.com" in (j.get("job_url") or "")]

    for job in targets:
        url = job.get("job_url", "")
        try:
            driver.get(url)
            time.sleep(3)

            easy_apply_btn = driver.find_elements(
                By.CSS_SELECTOR,
                "button.jobs-apply-button, .jobs-s-apply button, button[aria-label*='Easy Apply']",
            )
            if not easy_apply_btn:
                print(f"No Easy Apply: {job.get('title')} @ {job.get('company')}")
                continue

            easy_apply_btn[0].click()
            time.sleep(2)
            _fill_linkedin_form(driver, profile)

            submit_btn = driver.find_elements(
                By.CSS_SELECTOR, "button[aria-label='Submit application']"
            )
            if submit_btn:
                submit_btn[0].click()
                applied_count += 1
                print(f"Applied: {job.get('title')} @ {job.get('company')}")
                time.sleep(2)
            else:
                print(f"Review manually: {job.get('title')} @ {job.get('company')}")

        except Exception as e:
            print(f"Error on {job.get('title', '?')}: {e}")

    driver.quit()
    print(f"\nDone. Submitted {applied_count} LinkedIn Easy Apply applications.")


def _fill_linkedin_form(driver, profile: dict):
    from selenium.webdriver.common.by import By

    for f in driver.find_elements(By.CSS_SELECTOR, "input[id*='phoneNumber']"):
        if not f.get_attribute("value") and profile.get("phone"):
            f.clear()
            f.send_keys(profile["phone"])

    for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='number']"):
        label = (inp.get_attribute("aria-label") or "").lower()
        if ("year" in label or "experience" in label) and not inp.get_attribute("value"):
            inp.send_keys(str(profile.get("experience_years", 1)))

    for _ in range(5):
        time.sleep(1.5)
        next_btns = driver.find_elements(
            By.CSS_SELECTOR,
            "button[aria-label='Continue to next step'], button[aria-label='Review your application']",
        )
        if next_btns:
            next_btns[0].click()
        else:
            break


def generate_apply_packet(job: dict, profile: dict, resume_text: str) -> dict:
    _require_groq()
    prompt = f"""Given this job and candidate, generate an apply packet as JSON:
{{
  "tailored_headline": "2-line headline for this role",
  "cover_letter": "150-word cover letter",
  "resume_bullets": ["3 tailored bullet points"],
  "keywords_to_include": ["ATS keywords from the job"]
}}

Candidate: {json.dumps(profile)}
Resume: {resume_text[:1000]}
Job: {job.get('title')} at {job.get('company')}
Description: {str(job.get('description', ''))[:800]}

Return ONLY valid JSON.
"""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        response_format={"type": "json_object"},
    )
    return parse_json_response(resp.choices[0].message.content or "")


def run_packet_apply(jobs: list[dict], profile: dict, resume_text: str, limit: int = 5) -> int:
    import webbrowser

    count = 0
    for job in get_applyable_jobs(jobs)[:limit]:
        print(f"\nGenerating packet for {job.get('title')} @ {job.get('company')}...")
        packet = generate_apply_packet(job, profile, resume_text)
        safe_co = re.sub(r"[^\w-]", "_", job.get("company", "company"))[:40]
        filename = f"apply_{safe_co}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(packet, f, indent=2)
        if job.get("job_url"):
            webbrowser.open(job["job_url"])
        print(f"Packet saved: {filename}")
        print(f"Cover letter preview:\n{packet.get('cover_letter', '')[:200]}...")
        count += 1
    return count
