from models.product import Product
from repositories.interfaces.product import ProductRepositoryProtocol
from schemas.product import ProductCreate
from services.exceptions import NotFoundError


class ProductService:
    def __init__(self, repo: ProductRepositoryProtocol) -> None:
        self._repo = repo

    def list(
        self,
        skip: int = 0,
        limit: int = 25,
        category: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> list[Product]:
        return self._repo.get_all(skip=skip, limit=limit, category=category, sort_by=sort_by, sort_order=sort_order)

    def count(self, category: str | None = None) -> int:
        return self._repo.count(category=category)

    def get(self, id: int) -> Product:
        product = self._repo.get_by_id(id)
        if not product:
            raise NotFoundError(f"Product {id} not found")
        return product

    def create(self, data: ProductCreate) -> Product:
        return self._repo.create(data)
