from models.customer import Customer
from repositories.interfaces.customer import CustomerRepositoryProtocol
from schemas.customer import CustomerCreate
from services.exceptions import NotFoundError


class CustomerService:
    def __init__(self, repo: CustomerRepositoryProtocol) -> None:
        self._repo = repo

    def list(
        self,
        skip: int = 0,
        limit: int = 25,
        region: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> list[Customer]:
        return self._repo.get_all(skip=skip, limit=limit, region=region, sort_by=sort_by, sort_order=sort_order)

    def count(self, region: str | None = None) -> int:
        return self._repo.count(region=region)

    def get(self, id: int) -> Customer:
        customer = self._repo.get_by_id(id)
        if not customer:
            raise NotFoundError(f"Customer {id} not found")
        return customer

    def create(self, data: CustomerCreate) -> Customer:
        return self._repo.create(data)
