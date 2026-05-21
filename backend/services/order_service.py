from datetime import datetime

from models.order import Order
from repositories.interfaces.order import OrderRepositoryProtocol
from schemas.order import OrderCreate
from services.exceptions import NotFoundError


class OrderService:
    def __init__(self, repo: OrderRepositoryProtocol) -> None:
        self._repo = repo

    def list(
        self,
        skip: int = 0,
        limit: int = 25,
        customer_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> list[Order]:
        return self._repo.get_all(
            skip=skip,
            limit=limit,
            customer_id=customer_id,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    def count(
        self,
        customer_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> int:
        return self._repo.count(customer_id=customer_id, date_from=date_from, date_to=date_to)

    def get(self, id: int) -> Order:
        order = self._repo.get_by_id(id)
        if not order:
            raise NotFoundError(f"Order {id} not found")
        return order

    def create(self, data: OrderCreate) -> Order:
        return self._repo.create(data)
