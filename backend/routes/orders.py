from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from core.container import get_order_service
from core.dependencies import get_current_user
from models.order import Order
from models.user import User
from schemas.order import OrderCreate, OrderRead
from schemas.pagination import Page
from services.exceptions import NotFoundError
from services.order_service import OrderService

router = APIRouter()


@router.get("/", response_model=Page[OrderRead])
def list_orders(
    skip: int = 0,
    limit: int = Query(default=25, le=200),
    customer_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    service: OrderService = Depends(get_order_service),
    _: User = Depends(get_current_user),
) -> Page[OrderRead]:
    return Page(
        items=service.list(
            skip=skip,
            limit=limit,
            customer_id=customer_id,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
        total=service.count(customer_id=customer_id, date_from=date_from, date_to=date_to),
        skip=skip,
        limit=limit,
    )


@router.get("/{id}", response_model=OrderRead)
def get_order(
    id: int,
    service: OrderService = Depends(get_order_service),
    _: User = Depends(get_current_user),
) -> Order:
    try:
        return service.get(id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/", response_model=OrderRead, status_code=201)
def create_order(
    body: OrderCreate,
    service: OrderService = Depends(get_order_service),
    _: User = Depends(get_current_user),
) -> Order:
    return service.create(body)
