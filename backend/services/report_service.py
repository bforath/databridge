from repositories.interfaces.reports import ReportsRepositoryProtocol
from schemas.reports import (
    LowStockRow,
    MonthlyRevenueRow,
    SalesByRegionRow,
    StockAlertRow,
    StockHealthRow,
    StockProjectionRow,
    SummaryRow,
)


class ReportService:
    def __init__(self, repo: ReportsRepositoryProtocol) -> None:
        self._repo = repo

    def sales_by_region(self) -> list[SalesByRegionRow]:
        return self._repo.sales_by_region()

    def monthly_revenue(self, year: int | None = None) -> list[MonthlyRevenueRow]:
        return self._repo.monthly_revenue(year=year)

    def low_stock(self) -> list[LowStockRow]:
        return self._repo.low_stock()

    def stock_health(self, limit: int = 10) -> list[StockHealthRow]:
        return self._repo.stock_health(limit=limit)

    def stock_alerts(self, limit: int = 10) -> list[StockAlertRow]:
        return self._repo.stock_alerts(limit=limit)

    def stock_projections(self) -> list[StockProjectionRow]:
        return self._repo.stock_projections()

    def summary(self) -> SummaryRow:
        return self._repo.summary()
