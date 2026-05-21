from pydantic import BaseModel


class IngestionRun(BaseModel):
    id: int
    source: str
    status: str
    message: str | None
    total: int
    processed: int
    skipped: int
    remaining: int
    pct_complete: float
    started_at: str
    finished_at: str | None
    resumed_from_id: int | None
