from sqlalchemy import text
from sqlalchemy.orm import Session

from schemas.pipeline import IngestionRun


class PostgresPipelineRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_runs(self, limit: int = 20) -> list[IngestionRun]:
        rows = self._db.execute(
            text("""
                SELECT id, source, status, message, total, processed, skipped,
                       total - processed                                  AS remaining,
                       CASE WHEN total > 0
                            THEN ROUND(processed::numeric / total * 100, 1)
                            ELSE 0
                       END                                                AS pct_complete,
                       started_at,
                       finished_at,
                       resumed_from_id
                FROM workers.ingestion_runs
                ORDER BY started_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()

        return [
            IngestionRun(
                id=r.id,
                source=r.source,
                status=r.status,
                message=r.message,
                total=r.total,
                processed=r.processed,
                skipped=r.skipped,
                remaining=r.remaining,
                pct_complete=float(r.pct_complete),
                started_at=r.started_at.isoformat(),
                finished_at=r.finished_at.isoformat() if r.finished_at else None,
                resumed_from_id=r.resumed_from_id,
            )
            for r in rows
        ]
