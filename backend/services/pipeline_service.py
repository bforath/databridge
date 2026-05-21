from repositories.interfaces.pipeline import PipelineRepositoryProtocol
from schemas.pipeline import IngestionRun


class PipelineService:
    def __init__(self, repo: PipelineRepositoryProtocol) -> None:
        self._repo = repo

    def list_runs(self, limit: int = 20) -> list[IngestionRun]:
        return self._repo.list_runs(limit=limit)
