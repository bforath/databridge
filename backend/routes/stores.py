from fastapi import APIRouter, Depends, HTTPException, Query

from core.container import get_store_service
from core.dependencies import get_current_user
from models.user import User
from schemas.pagination import Page
from schemas.store import StoreDetail, StoreSummary
from services.exceptions import NotFoundError
from services.store_service import StoreService

router = APIRouter()


@router.get("/", response_model=Page[StoreSummary])
def list_stores(
    skip: int = 0,
    limit: int = Query(default=25, le=200),
    region: str | None = None,
    search: str | None = None,
    low_stock_only: bool = False,
    service: StoreService = Depends(get_store_service),
    _: User = Depends(get_current_user),
) -> Page[StoreSummary]:
    return Page(
        items=service.list(skip=skip, limit=limit, region=region, search=search, low_stock_only=low_stock_only),
        total=service.count(region=region, search=search, low_stock_only=low_stock_only),
        skip=skip,
        limit=limit,
    )


@router.get("/{id}", response_model=StoreDetail)
def get_store(
    id: int,
    service: StoreService = Depends(get_store_service),
    _: User = Depends(get_current_user),
) -> StoreDetail:
    try:
        return service.get(id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
