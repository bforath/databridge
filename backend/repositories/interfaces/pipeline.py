from typing import Protocol

from schemas.pipeline import IngestionRun


class PipelineRepositoryProtocol(Protocol):
    def list_runs(self, limit: int = 20) -> list[IngestionRun]: ...
