import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from insert_builder.config.settings import settings

logger = logging.getLogger(__name__)


def send_email(kind: str, tenant, target, error: str | None = None) -> None:
    """kind is 'success' or 'failure'. target is a TblDistribution or
    TblSubdistribution. Unlike template_builder's report.py, there's no
    per-tenant recipient (typesetter/user email) anywhere in insert_builder's
    schema — everything goes to settings.developer_email, the only verified
    recipient this tool actually has."""
    label = getattr(target, "Name", None) or getattr(target, "SubDistributionName", None)

    if kind == "success":
        body = f"Build completed successfully.\nTenant: {tenant.name}\nDistribution: {label}"
        _send(f"Insert Builder — {label} completed", body)
    elif kind == "failure":
        body = (
            f"Build failed.\nTenant: {tenant.name}\nDistribution: {label}\n\nError:\n{error}"
        )
        _send(f"Insert Builder — {label} FAILED", body)


def safe_send_email(kind: str, tenant, target, error: str | None = None) -> None:
    """Never lets an email failure (e.g. unreachable SMTP server) block the
    build's own success/failure handling — the build result is already final
    by the time this runs, a failed notification should only be logged."""
    try:
        send_email(kind, tenant, target, error)
    except Exception as e:
        logger.error("Failed to send '%s' notification email: %s", kind, e, exc_info=True)


def _send(subject: str, body: str) -> None:
    if not settings.email_enabled:
        logger.info("Email disabled; skipped sending '%s'", subject)
        return

    msg = MIMEMultipart()
    msg["From"] = settings.from_email
    msg["To"] = settings.developer_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(settings.smtp_host, int(settings.smtp_port)) as server:
        server.sendmail(settings.from_email, settings.developer_email, msg.as_string())
