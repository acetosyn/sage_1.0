# SERVICE: SAGE Email Notifications
# Direct SMTP sender compatible with both SAGE SMTP_* and the existing EMIS MAIL_* environment names; in-app notifications remain primary.

import html
import smtplib
from email.message import EmailMessage
from threading import Thread


def _deliver(app, recipient, subject, text_body, html_body=None):
    host, port = app.config.get("SMTP_HOST"), int(app.config.get("SMTP_PORT", 587) or 587); username, password = app.config.get("SMTP_USERNAME"), app.config.get("SMTP_PASSWORD")
    sender = app.config.get("SMTP_FROM_EMAIL") or username; use_tls, use_ssl = bool(app.config.get("SMTP_USE_TLS", True)), bool(app.config.get("SMTP_USE_SSL", False))
    if not app.config.get("EMAIL_NOTIFICATIONS_ENABLED") or not host or not sender or not recipient: return False
    try:
        message = EmailMessage(); message["Subject"], message["From"], message["To"], message["Reply-To"] = subject, sender, recipient, sender; message.set_content(text_body or "")
        if html_body: message.add_alternative(html_body, subtype="html")
        smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_class(host, port, timeout=20) as smtp:
            smtp.ehlo()
            if use_tls and not use_ssl: smtp.starttls(); smtp.ehlo()
            if username and password: smtp.login(username, password)
            smtp.send_message(message)
        app.logger.info("SAGE email sent to %s", recipient); return True
    except Exception as error: app.logger.warning("SAGE email notification failed for %s: %s", recipient, error); return False


def send_email(app, recipient, subject, body, html_body=None):
    """Queue SMTP outside the request thread so a slow mail provider never blocks a SAGE action."""
    if not app.config.get("EMAIL_NOTIFICATIONS_ENABLED") or not recipient: return False
    Thread(target=_deliver, args=(app, recipient, subject, body, html_body), daemon=True).start(); return True


def send_staff_invitation_email(app, invitation, invite_url, inviter):
    """Send the private SAGE onboarding link while preserving the existing copy-link invitation workflow."""
    organization = invitation.organization.name if invitation.organization else (inviter.organization.name if inviter and inviter.organization else "your organization"); department = invitation.department.name if invitation.department else "Assigned department"; name = " ".join(part for part in [invitation.first_name, invitation.last_name] if part).strip() or "there"
    role = invitation.role.replace("_", " ").title(); safe_url, safe_name, safe_org, safe_department, safe_role = map(html.escape, [invite_url, name, organization, department, role])
    subject = f"You're invited to join {organization} on SAGE"
    text = f"Hello {name},\n\n{inviter.display_name} invited you to join {organization} on SAGE.\nDepartment: {department}\nAccess role: {role}\n\nCreate your staff account using this private link:\n{invite_url}\n\nThe link expires automatically. If you were not expecting this invitation, you can ignore this email.\n\nSAGE"
    html_body = f'''<div style="font-family:Inter,Arial,sans-serif;background:#f5f8fc;padding:28px;color:#132236"><div style="max-width:620px;margin:auto;background:#fff;border:1px solid #dce6f2;border-radius:18px;overflow:hidden"><div style="padding:22px 26px;background:#10243b;color:#fff"><div style="font-size:24px;font-weight:800;letter-spacing:.04em">SAGE</div><div style="margin-top:5px;color:#b9c9dc;font-size:13px">Secure staff invitation</div></div><div style="padding:26px"><p style="margin-top:0">Hello <b>{safe_name}</b>,</p><p>{html.escape(inviter.display_name)} invited you to join <b>{safe_org}</b> on SAGE.</p><div style="margin:18px 0;padding:14px;border:1px solid #dce6f2;border-radius:12px;background:#f8fbff"><div><b>Department:</b> {safe_department}</div><div style="margin-top:6px"><b>Access role:</b> {safe_role}</div></div><a href="{safe_url}" style="display:inline-block;padding:12px 18px;border-radius:10px;background:#2f63ff;color:white;text-decoration:none;font-weight:700">Join SAGE & create account</a><p style="margin:20px 0 6px;color:#6d7c91;font-size:12px">Or copy this private link:</p><p style="word-break:break-all;font-size:12px;color:#3157a4">{safe_url}</p><p style="margin-bottom:0;color:#7c8999;font-size:12px">This invitation expires automatically. Ignore this message if you were not expecting it.</p></div></div></div>'''
    return send_email(app, invitation.email, subject, text, html_body)
