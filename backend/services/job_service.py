import uuid

from core.events import dispatch
from models.job import Job, JobStatus
from repositories.interfaces.job import JobRepositoryProtocol
from services.exceptions import NotFoundError, ValidationError
from writers.interfaces.writer import WriterProtocol

_VALID_EXPORT_RESOURCES = frozenset({"customers", "products", "orders"})


class JobService:
    def __init__(self, repo: JobRepositoryProtocol, writer: WriterProtocol) -> None:
        self._repo = repo
        self._writer = writer

    def dispatch_report(self) -> tuple[str, JobStatus]:
        job_id = str(uuid.uuid4())
        job = self._repo.create(job_id, "generate_summary_report", {})
        dispatch("report.generate", {"job_id": job_id})
        return job.id, JobStatus(job.status)

    def dispatch_export(self, resource: str, user_email: str) -> tuple[str, JobStatus]:
        if resource not in _VALID_EXPORT_RESOURCES:
            raise ValidationError(f"Unknown resource: {resource}")
        job_id = str(uuid.uuid4())
        payload = {"resource": resource, "email": user_email, "format": self._writer.extension}
        job = self._repo.create(job_id, "export_resource", payload)
        dispatch("export.requested", {"job_id": job_id, **payload})
        return job.id, JobStatus(job.status)

    def get(self, job_id: str) -> Job:
        job = self._repo.get(job_id)
        if not job:
            raise NotFoundError(f"Job {job_id} not found")
        return job

    def list(self, skip: int = 0, limit: int = 25) -> list[Job]:
        return self._repo.list(skip=skip, limit=limit)
