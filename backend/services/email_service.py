import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
import logging

from dotenv import load_dotenv

app_logger = logging.getLogger("sentinel.email")

class EmailService:
    @staticmethod
    def send_email(to_email, subject, html_content, text_content=None):
        """
        Sends an email using standard SMTP.
        Connects via Gmail SMTP (or configured SMTP host).
        """
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
        load_dotenv(dotenv_path=env_path, override=True)

        smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", 587))
        smtp_user = os.environ.get("SMTP_USER", "probot12309@gmail.com")
        smtp_password = os.environ.get("SMTP_PASSWORD")
        smtp_use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
        from_email = os.environ.get("ALERT_FROM_EMAIL", smtp_user or "probot12309@gmail.com")

        if not text_content:
            text_content = html_content

        result = {
            "success": True,
            "recipient": to_email,
            "subject": subject,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "simulated"
        }

        # If live SMTP password is provided, attempt network transmission
        if smtp_host and smtp_user and smtp_password:
            clean_password = smtp_password.replace(" ", "").strip()
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = f"Sentinel-Trace SOC Alerts <{from_email}>"
                msg["To"] = to_email

                part1 = MIMEText(text_content, "plain")
                part2 = MIMEText(html_content, "html")
                msg.attach(part1)
                msg.attach(part2)

                server = smtplib.SMTP(smtp_host, smtp_port, timeout=12)
                if smtp_use_tls:
                    server.starttls()
                server.login(smtp_user, clean_password)
                server.sendmail(from_email, [to_email], msg.as_string())
                server.quit()

                result["mode"] = "smtp_delivered"
                result["message"] = f"Email delivered successfully to {to_email}"
                app_logger.info(f"Successfully transmitted SMTP email notification to: {to_email}")
                return result, None
            except Exception as e:
                err_msg = str(e)
                app_logger.warning(f"SMTP transmission failed: {err_msg}")
                result["mode"] = "smtp_error"
                result["error"] = err_msg
                result["message"] = f"SMTP error ({err_msg}). Check Google App Password."
                return result, err_msg
        else:
            result["mode"] = "smtp_credentials_needed"
            result["message"] = f"Recipient set to {to_email}. Please provide Google App Password in .env to deliver live."
            app_logger.info(f"[EMAIL PREPARED] To: {to_email} | Subject: '{subject}' | Mode: credentials_needed")
            return result, None

    @classmethod
    def send_alert_notification(cls, alert_dict, user_email=None, action="Acknowledged"):
        """
        Generates and dispatches an official SOC Alert Notification email
        when an alert is Acknowledged, Resolved, or Dismissed.
        """
        alert_id = alert_dict.get("id") or alert_dict.get("alert_id") or "ALT-UNKNOWN"
        severity = alert_dict.get("severity") or "Warning"
        message = alert_dict.get("message") or alert_dict.get("title") or "Industrial Security Alert"
        source = alert_dict.get("source") or alert_dict.get("category") or "OT-Network"
        timestamp = alert_dict.get("timestamp") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        fallback_email = os.environ.get("ALERT_NOTIFICATION_EMAIL") or os.environ.get("SMTP_USER") or "probot12309@gmail.com"
        if not user_email or "@" not in user_email or "sentineltrace" in user_email:
            recipient = fallback_email
        else:
            recipient = user_email

        subject = f"[Sentinel-Trace SOC Alert] {action}: {alert_id} ({severity.upper()})"
        badge_color = "#ef4444" if severity == "Critical" else ("#f59e0b" if severity == "Warning" else "#3b82f6")

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
            .header {{ background-color: #1e293b; padding: 24px; text-align: left; }}
            .header h1 {{ color: #ffffff; font-size: 20px; margin: 0; }}
            .header p {{ color: #fa7b7b; font-size: 13px; margin: 4px 0 0; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}
            .body {{ padding: 24px; }}
            .badge {{ display: inline-block; padding: 4px 10px; border-radius: 4px; color: #ffffff; font-size: 12px; font-weight: 700; background-color: {badge_color}; }}
            .action-banner {{ background: #f1f5f9; border-left: 4px solid #fa7b7b; padding: 12px 16px; margin: 16px 0; border-radius: 0 4px 4px 0; }}
            .details-table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
            .details-table td {{ padding: 8px 0; border-bottom: 1px solid #f1f5f9; font-size: 14px; }}
            .details-table td.label {{ color: #64748b; font-weight: 600; width: 140px; }}
            .details-table td.value {{ color: #0f172a; font-family: monospace; font-size: 13px; }}
            .footer {{ background-color: #f8fafc; padding: 16px 24px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center; }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header">
              <h1>Sentinel-Trace OT Defense</h1>
              <p>Security Operations Center Notification</p>
            </div>
            <div class="body">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span class="badge">{severity.upper()}</span>
                <span style="font-size: 12px; color: #64748b;">{timestamp}</span>
              </div>
              <div class="action-banner">
                <strong>Event Status Update:</strong> Alert marked as <strong>{action}</strong> by <code>{recipient}</code>.
              </div>
              <h2 style="font-size: 16px; color: #1e293b; margin: 16px 0 8px;">{message}</h2>
              <table class="details-table">
                <tr><td class="label">Alert Identifier:</td><td class="value">{alert_id}</td></tr>
                <tr><td class="label">Subsystem / Host:</td><td class="value">{source}</td></tr>
                <tr><td class="label">Action Recorded:</td><td class="value">{action}</td></tr>
                <tr><td class="label">Recipient Account:</td><td class="value">{recipient}</td></tr>
              </table>
            </div>
            <div class="footer">
              This automated message was generated by Sentinel-Trace Security Engine. All rights reserved.
            </div>
          </div>
        </body>
        </html>
        """

        text_content = f"""
Sentinel-Trace Security Operations Center Notification
=====================================================
Status Update: Alert {alert_id} was marked as {action.upper()} by {recipient}.

Details:
- Alert ID: {alert_id}
- Severity: {severity}
- Source: {source}
- Message: {message}
- Timestamp: {timestamp}

This is an automated notification from Sentinel-Trace.
        """

        return cls.send_email(to_email=recipient, subject=subject, html_content=html_content, text_content=text_content)
