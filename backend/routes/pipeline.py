from fastapi import APIRouter, Depends

from core.container import get_pipeline_service
from core.dependencies import get_current_user
from models.user import User
from schemas.pipeline import IngestionRun
from services.pipeline_service import PipelineService

router = APIRouter()


@router.get("/runs", response_model=list[IngestionRun])
def list_runs(
    limit: int = 20,
    _: User = Depends(get_current_user),
    service: PipelineService = Depends(get_pipeline_service),
) -> list[IngestionRun]:
    return service.list_runs(limit=limit)
