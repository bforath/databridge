from repositories.interfaces.store import StoreRepositoryProtocol
from schemas.store import StoreDetail, StoreSummary
from services.exceptions import NotFoundError


class StoreService:
    def __init__(self, repo: StoreRepositoryProtocol) -> None:
        self._repo = repo

    def list(
        self,
        skip: int = 0,
        limit: int = 25,
        region: str | None = None,
        search: str | None = None,
        low_stock_only: bool = False,
    ) -> list[StoreSummary]:
        return self._repo.get_all(skip=skip, limit=limit, region=region, search=search, low_stock_only=low_stock_only)

    def count(
        self,
        region: str | None = None,
        search: str | None = None,
        low_stock_only: bool = False,
    ) -> int:
        return self._repo.count(region=region, search=search, low_stock_only=low_stock_only)

    def get(self, id: int) -> StoreDetail:
        store = self._repo.get_by_id(id)
        if not store:
            raise NotFoundError(f"Store {id} not found")
        return store
