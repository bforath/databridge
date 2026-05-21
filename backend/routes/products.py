from fastapi import APIRouter, Depends, HTTPException, Query

from core.container import get_product_service
from core.dependencies import get_current_user
from models.product import Product
from models.user import User
from schemas.pagination import Page
from schemas.product import ProductCreate, ProductRead
from services.exceptions import NotFoundError
from services.product_service import ProductService

router = APIRouter()


@router.get("/", response_model=Page[ProductRead])
def list_products(
    skip: int = 0,
    limit: int = Query(default=25, le=200),
    category: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    service: ProductService = Depends(get_product_service),
    _: User = Depends(get_current_user),
) -> Page[ProductRead]:
    return Page(
        items=service.list(skip=skip, limit=limit, category=category, sort_by=sort_by, sort_order=sort_order),
        total=service.count(category=category),
        skip=skip,
        limit=limit,
    )


@router.get("/{id}", response_model=ProductRead)
def get_product(
    id: int,
    service: ProductService = Depends(get_product_service),
    _: User = Depends(get_current_user),
) -> Product:
    try:
        return service.get(id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/", response_model=ProductRead, status_code=201)
def create_product(
    body: ProductCreate,
    service: ProductService = Depends(get_product_service),
    _: User = Depends(get_current_user),
) -> Product:
    return service.create(body)
