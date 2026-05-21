import logging
from collections.abc import Callable

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session

from core import storage
from core.celery_app import celery_app
from core.container import get_mailer, get_order_repo, get_product_repo, make_customer_repo
from core.database import SessionLocal
from core.events import on
from repositories.interfaces.customer import CustomerRepositoryProtocol
from repositories.interfaces.order import OrderRepositoryProtocol
from repositories.interfaces.product import ProductRepositoryProtocol
from repositories.postgres.job import PostgresJobRepository
from writers.factory import get_writer

logger = logging.getLogger(__name__)

_ExportRepo = CustomerRepositoryProtocol | ProductRepositoryProtocol | OrderRepositoryProtocol
_REPO_FACTORY: dict[str, Callable[[Session], _ExportRepo]] = {
    "customers": make_customer_repo,
    "products": get_product_repo,
    "orders": get_order_repo,
}


def _send_via_s3(email_to: str, resource: str, job_id: str, data: bytes, writer) -> str | None:  # type: ignore[no-untyped-def]
    """
    Upload to S3 and email a pre-signed download link.
    Returns the S3 key on success, None if S3 is unavailable.
    """
    try:
        key = f"exports/{job_id}/{resource}_export.{writer.extension}"
        storage.upload(key, data, writer.content_type)
        download_url = storage.presign(key)
        get_mailer().send(
            to=email_to,
            subject=f"Databridge — {resource.capitalize()} Export Ready",
            body=(
                f"Your {resource} export is ready.\n\n"
                f"Download: {download_url}\n\n"
                "Link expires in 24 hours."
            ),
        )
        return key
    except (BotoCoreError, ClientError, Exception) as e:
        logger.warning("S3 upload failed, falling back to email attachment: %s", e)
        return None


def _send_via_attachment(email_to: str, resource: str, rows: int, data: bytes, writer) -> None:  # type: ignore[no-untyped-def]
    """Email the export file as a direct attachment."""
    get_mailer().send(
        to=email_to,
        subject=f"Databridge — {resource.capitalize()} Export",
        body=f"Your {resource} export is attached ({rows} records).",
        attachment=data,
        filename=f"{resource}_export.{writer.extension}",
        content_type=writer.content_type,
    )


@on("export.requested")
@celery_app.task
def export_resource(payload: dict) -> dict:
    job_id = payload["job_id"]
    resource = payload["resource"]
    email_to = payload["email"]
    fmt = payload.get("format", "xlsx")

    db = SessionLocal()
    repo = PostgresJobRepository(db)

    try:
        repo.set_running(job_id)

        resource_repo = _REPO_FACTORY[resource](db)
        columns, rows = resource_repo.export_all()
        writer = get_writer(fmt)
        data = writer.write(columns, rows)

        # Try S3 first — fall back to attachment if LocalStack isn't running
        # or real AWS credentials aren't configured.
        s3_key = _send_via_s3(email_to, resource, job_id, data, writer)
        if s3_key is None:
            _send_via_attachment(email_to, resource, len(rows), data, writer)

        result = {
            "resource": resource,
            "rows": len(rows),
            "emailed_to": email_to,
            **({"s3_key": s3_key} if s3_key else {"delivery": "attachment"}),
        }
        repo.set_success(job_id, result)
        return result

    except Exception as e:
        repo.set_failed(job_id, str(e))
        raise
    finally:
        db.close()
