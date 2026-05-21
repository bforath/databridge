from fastapi import APIRouter, Depends, HTTPException, Query

from core.container import get_customer_service
from core.dependencies import get_current_user
from models.customer import Customer
from models.user import User
from schemas.customer import CustomerCreate, CustomerRead
from schemas.pagination import Page
from services.customer_service import CustomerService
from services.exceptions import NotFoundError

router = APIRouter()


@router.get("/", response_model=Page[CustomerRead])
def list_customers(
    skip: int = 0,
    limit: int = Query(default=25, le=200),
    region: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    service: CustomerService = Depends(get_customer_service),
    _: User = Depends(get_current_user),
) -> Page[CustomerRead]:
    return Page(
        items=service.list(skip=skip, limit=limit, region=region, sort_by=sort_by, sort_order=sort_order),
        total=service.count(region=region),
        skip=skip,
        limit=limit,
    )


@router.get("/{id}", response_model=CustomerRead)
def get_customer(
    id: int,
    service: CustomerService = Depends(get_customer_service),
    _: User = Depends(get_current_user),
) -> Customer:
    try:
        return service.get(id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/", response_model=CustomerRead, status_code=201)
def create_customer(
    body: CustomerCreate,
    service: CustomerService = Depends(get_customer_service),
    _: User = Depends(get_current_user),
) -> Customer:
    return service.create(body)
