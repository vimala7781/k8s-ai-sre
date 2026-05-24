# notifier.py
# Phase 4 - M4.3
# Job: send email alerts via Gmail for medium and high risk diagnoses.
# Uses Python's built-in smtplib — no extra library needed.
#
# Why email and not a direct fix?
# Medium/high risk means Claude found a fix but it's too dangerous
# to auto-apply. A human needs to review the fix plan and decide.
# The email contains everything they need to act immediately.

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SENDER   = os.getenv("GMAIL_SENDER")
PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
RECEIVER = os.getenv("GMAIL_RECEIVER")

# ── Build email body ─────────────────────────────────────────────
# We build both a plain text and HTML version.
# Email clients show HTML if supported, plain text as fallback.

def build_email_body(pod_name, diagnosis, remediation_result=None):
    timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    risk_level = diagnosis.get("risk_level", "unknown").upper()
    root_cause = diagnosis.get("root_cause", "N/A")
    confidence = diagnosis.get("confidence", "N/A")
    fix_steps  = diagnosis.get("fix_steps", [])
    sources    = diagnosis.get("sources", [])
    searches   = diagnosis.get("search_queries_used", [])

    # ── Plain text version ───────────────────────────────────────
    plain = f"""
K8S AI SRE ALERT
================
Time:       {timestamp}
Pod:        {pod_name}
Risk:       {risk_level}
Confidence: {confidence}

ROOT CAUSE:
{root_cause}

FIX STEPS:
"""
    for i, step in enumerate(fix_steps, 1):
        plain += f"{i}. {step}\n"

    if remediation_result:
        plain += f"\nAUTO-REMEDIATION RESULT:\n{remediation_result}\n"

    plain += f"\nSEARCHES USED:\n"
    for q in searches:
        plain += f"  • {q}\n"

    plain += f"\nSOURCES:\n"
    for s in sources:
        plain += f"  • {s}\n"

    # ── HTML version ─────────────────────────────────────────────
    risk_color = {
        "LOW":    "#22c55e",   # green
        "MEDIUM": "#f59e0b",   # amber
        "HIGH":   "#ef4444",   # red
    }.get(risk_level, "#6b7280")

    fix_steps_html = "".join(
        f"<li style='margin:6px 0'>{step}</li>" for step in fix_steps
    )
    sources_html = "".join(
        f"<li><a href='{s}'>{s}</a></li>" for s in sources
    )
    searches_html = "".join(
        f"<li><code>{q}</code></li>" for q in searches
    )

    remediation_html = ""
    if remediation_result:
        remediation_html = f"""
        <div style='background:#f0fdf4;border-left:4px solid #22c55e;padding:12px;margin:16px 0'>
            <strong>Auto-remediation result:</strong><br>{remediation_result}
        </div>"""

    html = f"""
    <div style='font-family:sans-serif;max-width:680px;margin:0 auto'>
        <div style='background:{risk_color};color:white;padding:16px 24px;border-radius:8px 8px 0 0'>
            <h2 style='margin:0'>⚠️ K8S AI SRE Alert — {risk_level} RISK</h2>
            <p style='margin:4px 0 0 0;opacity:0.9'>{timestamp}</p>
        </div>

        <div style='border:1px solid #e5e7eb;border-top:none;padding:24px;border-radius:0 0 8px 8px'>
            <table style='width:100%;border-collapse:collapse;margin-bottom:16px'>
                <tr><td style='padding:6px;color:#6b7280'>Pod</td>
                    <td style='padding:6px;font-weight:bold'>{pod_name}</td></tr>
                <tr><td style='padding:6px;color:#6b7280'>Confidence</td>
                    <td style='padding:6px'>{confidence}</td></tr>
            </table>

            <div style='background:#fef9c3;border-left:4px solid #eab308;padding:12px;margin:16px 0'>
                <strong>Root cause:</strong><br>{root_cause}
            </div>

            {remediation_html}

            <h3>🔧 Fix steps</h3>
            <ol style='padding-left:20px'>{fix_steps_html}</ol>

            <h3>🔎 Searches Claude used</h3>
            <ul>{searches_html}</ul>

            <h3>📚 Sources</h3>
            <ul>{sources_html}</ul>

            <hr style='border:none;border-top:1px solid #e5e7eb;margin:24px 0'>
            <p style='color:#9ca3af;font-size:12px'>
                Sent by k8s-ai-sre autonomous agent · namespace: k8s-ai-sre
            </p>
        </div>
    </div>
    """
    return plain, html


# ── Send the email ───────────────────────────────────────────────
# smtplib is Python's built-in email library.
# SMTP_SSL opens an encrypted connection to Gmail on port 465.
# No library install needed — it ships with Python.

def send_alert(pod_name, diagnosis, remediation_result=None):
    if not all([SENDER, PASSWORD, RECEIVER]):
        print("[!] Gmail credentials missing in .env — skipping email alert")
        return False

    risk_level = diagnosis.get("risk_level", "unknown").upper()
    subject    = f"[K8S ALERT] {risk_level} RISK — {pod_name} needs attention"

    plain, html = build_email_body(pod_name, diagnosis, remediation_result)

    # Build the email object
    # MIMEMultipart("alternative") = email with both plain + HTML versions
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER
    msg["To"]      = RECEIVER

    # Attach both versions — email client picks the best one
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))

    try:
        # Connect to Gmail's SMTP server with SSL encryption
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER, PASSWORD)        # authenticate
            server.sendmail(SENDER, RECEIVER, msg.as_string())

        print(f"\n📧 EMAIL SENT: {subject}")
        return True

    except Exception as e:
        print(f"\n[!] Email failed: {e}")
        return False
