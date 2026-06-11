"""
emailer.py - HTML digest rendering + SMTP delivery.

Builds the tiered HTML report (Global = 4 tiers, India = 3 priority buckets) and sends
it via Gmail SMTP. Credentials come from env first (SENDER_EMAIL / RECIPIENT_EMAIL /
GMAIL_APP_PASSWORD), config second - real addresses stay out of the public YAML.

Test seam: tests patch `emailer.smtplib.SMTP`. The `_html_escape` import is aliased
because a local var named `html` inside send_email would otherwise shadow the html module.
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from html import escape as _html_escape  # module-level alias - NOT `import html`, because send_email
                                         # uses a local variable named `html` that would shadow the module.


def send_email(subject, jobs, config):
    if not jobs: return False
    # Escape scraped values before embedding in HTML (e.g. "R&D", "QA <Contract>"). Uses the
    # module-level _html_escape alias - the local `html` string var below shadows the html module.
    def esc(v):
        return _html_escape(str(v if v is not None else ""))
    # Email addresses come from env first (kept out of the public config); config is the fallback.
    sender_email = os.environ.get("SENDER_EMAIL") or config["email"]["sender_email"]
    sender_password = os.environ.get("GMAIL_APP_PASSWORD") or config["email"].get("app_password")
    recipient_email = os.environ.get("RECIPIENT_EMAIL") or config["email"]["recipient_email"]
    if not sender_password or "qwerty" in sender_password:
        print(f"  [SKIP] Skipping email: Credentials missing.")
        return False

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = subject

    # LOAD UI STRATEGY FROM CONFIG
    india_tier_cfg = config["search"].get("india_tiers", {})
    global_tier_cfg = config["search"].get("global_tiers", {})

    html = f"<div style='font-family: Arial, sans-serif; color: #333; max-width: 800px; margin: auto;'>"
    html += f"<div style='background-color: #2c3e50; color: white; padding: 20px; border-radius: 8px 8px 0 0;'>"
    html += f"<h1 style='margin: 0; font-size: 24px;'>{subject}</h1>"
    html += f"<p style='margin: 5px 0 0; opacity: 0.8;'>EM/Director Intelligence Report | {datetime.now().strftime('%Y-%m-%d')}</p></div>"

    if "Global" in subject:
        # Group jobs by Tier
        tiers = {"tier1": [], "tier2": [], "tier3": [], "tier4": []}
        for j in jobs:
            s = j.get('site', '').lower()
            tier_key = "tier1" if s.startswith("ats") else "tier1" if s in ["deel", "remote.com"] else \
                       "tier2" if s in ["yc", "wellfound", "arc.dev", "otta"] else \
                       "tier3" if s in ["wwr", "js_remotely"] else "tier4"
            tiers[tier_key].append(j)

        for t_key in ["tier1", "tier2", "tier3", "tier4"]:
            if not tiers[t_key]: continue
            t_info = global_tier_cfg.get(t_key, {"name": t_key, "color": "#333", "btn": "Link"})
            html += f"<div style='margin-top: 30px;'>"
            html += f"<h3 style='color: {t_info['color']}; border-left: 5px solid {t_info['color']}; padding-left: 10px; margin-bottom: 15px;'>{t_info['name']}</h3>"
            html += "<table border='0' cellpadding='10' style='border-collapse: collapse; width: 100%; box-shadow: 0 2px 5px rgba(0,0,0,0.1);'>"
            html += f"<tr style='background-color: {t_info['color']}; color: white;'><th>Title</th><th>Company</th><th>Location</th><th>Signal</th><th style='width: 80px;'>Action</th></tr>"
            for job in tiers[t_key]:
                html += f"<tr style='border-bottom: 1px solid #eee;'>"
                html += f"<td><b>{esc(job.get('title'))}</b></td>"
                html += f"<td>{esc(job.get('company'))}</td>"
                html += f"<td>{esc(job.get('location'))}</td>"
                html += f"<td style='color: #7f8c8d; font-size: 0.85em;'>{esc(job.get('signal'))}</td>"
                html += f"<td style='text-align: center;'><a href='{esc(job.get('job_url'))}' style='background-color: {t_info['color']}; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 0.85em;'>{t_info['btn']}</a></td>"
                html += f"</tr>"
            html += "</table></div>"
    else:
        # --- TRI-CATEGORY INDIA BUCKETING ---
        in_jobs = {"prio1": [], "prio2": [], "prio3": []}
        for j in jobs:
            loc = j.get('location', '').lower()
            if "hybrid" in loc or "remote-local" in loc: in_jobs["prio1"].append(j)
            elif "india-wfa" in loc or "wfa" in loc: in_jobs["prio2"].append(j)
            else: in_jobs["prio3"].append(j)

        for p_key in sorted(in_jobs.keys()):
            if not in_jobs[p_key]: continue
            t_data = india_tier_cfg.get(p_key, {"name": p_key, "color": "#333"})
            html += f"<div style='margin-top: 30px;'>"
            html += f"<h3 style='color: {t_data['color']}; border-left: 5px solid {t_data['color']}; padding-left: 10px; margin-bottom: 15px;'>{t_data['name']}</h3>"
            html += "<table border='0' cellpadding='10' style='border-collapse: collapse; width: 100%; box-shadow: 0 2px 5px rgba(0,0,0,0.1);'>"
            html += f"<tr style='background-color: {t_data['color']}; color: white;'><th>Title</th><th>Company</th><th>Location (Signal)</th><th>Site</th><th style='width: 80px;'>Action</th></tr>"
            for job in in_jobs[p_key]:
                html += f"<tr style='border-bottom: 1px solid #eee;'>"
                html += f"<td><b>{esc(job.get('title'))}</b></td>"
                html += f"<td>{esc(job.get('company'))}</td>"
                html += f"<td style='color: #666; font-size: 0.9em;'>{esc(job.get('location'))}</td>"
                html += f"<td style='color: #7f8c8d; font-size: 0.85em; text-transform: capitalize;'>{esc(job.get('site'))}</td>"
                html += f"<td style='text-align: center;'><a href='{esc(job.get('job_url'))}' style='background-color: #3498db; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 0.85em;'>Apply</a></td>"
                html += f"</tr>"
            html += "</table></div>"

    html += "<div style='margin-top: 30px; text-align: center; color: #95a5a6; font-size: 0.8em; border-top: 1px solid #eee; padding-top: 20px;'>"
    html += "This is an automated intelligence report from your Job Alert Bot v1.2. Hub Logic: Power 6 Tiered Grid.</div></div>"

    msg.attach(MIMEText(html, "html"))

    try:
        print(f"  [MAIL] Connecting to SMTP for '{subject}'...")
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        print(f"  [SUCCESS] Email sent.")
        return True
    except Exception as e:
        print(f"  [ERROR] Email failed: {str(e)[:100]}")
        return False
