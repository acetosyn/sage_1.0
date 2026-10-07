# SERVICE: SAGE Email Notifications
# Sends optional SMTP alerts for important staff/finance/procurement events; in-app notifications remain primary and always work.

import smtplib
from email.message import EmailMessage
from threading import Thread


def _deliver(app, recipient, subject, body):
    host, port = app.config.get("SMTP_HOST"), int(app.config.get("SMTP_PORT", 587) or 587)
    username, password, sender = app.config.get("SMTP_USERNAME"), app.config.get("SMTP_PASSWORD"), app.config.get("SMTP_FROM_EMAIL") or app.config.get("SMTP_USERNAME")
    if not app.config.get("EMAIL_NOTIFICATIONS_ENABLED") or not host or not sender or not recipient: return
    try:
        message = EmailMessage(); message["Subject"], message["From"], message["To"] = subject, sender, recipient; message.set_content(body)
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            if app.config.get("SMTP_USE_TLS", True): smtp.starttls(); smtp.ehlo()
            if username and password: smtp.login(username, password)
            smtp.send_message(message)
    except Exception as error: app.logger.warning("SAGE email notification failed: %s", error)


def send_email(app, recipient, subject, body):
    """Send outside the request thread so SMTP delays never block a SAGE action."""
    if not app.config.get("EMAIL_NOTIFICATIONS_ENABLED"): return
    Thread(target=_deliver, args=(app, recipient, subject, body), daemon=True).start()
