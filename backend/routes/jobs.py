from fastapi import APIRouter, Depends, HTTPException

from core.container import get_job_service
from core.dependencies import get_current_user
from models.job import Job
from models.user import User
from schemas.job import DispatchResponse, JobOut
from services.exceptions import NotFoundError, ValidationError
from services.job_service import JobService

router = APIRouter()


@router.post("/dispatch/report", response_model=DispatchResponse)
def dispatch_report(
    _: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> DispatchResponse:
    """Enqueue a full summary report regeneration."""
    job_id, status = service.dispatch_report()
    return DispatchResponse(job_id=job_id, status=status)


@router.post("/dispatch/export", response_model=DispatchResponse)
def dispatch_export(
    resource: str,
    current_user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> DispatchResponse:
    """Enqueue a full dataset export. Result is emailed to the requesting user."""
    try:
        job_id, status = service.dispatch_export(resource, current_user.email)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return DispatchResponse(job_id=job_id, status=status)


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: str,
    _: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> Job:
    """Poll job status. Returns current state including result or error once complete."""
    try:
        return service.get(job_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/", response_model=list[JobOut])
def list_jobs(
    skip: int = 0,
    limit: int = 25,
    _: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> list[Job]:
    return service.list(skip=skip, limit=limit)
