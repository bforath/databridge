from fastapi import APIRouter, Depends

from core.container import get_report_service
from core.dependencies import get_current_user
from models.user import User
from schemas.reports import (
    LowStockRow,
    MonthlyRevenueRow,
    SalesByRegionRow,
    StockAlertRow,
    StockHealthRow,
    StockProjectionRow,
    SummaryRow,
)
from services.report_service import ReportService

router = APIRouter()


@router.get("/sales/by-region", response_model=list[SalesByRegionRow])
def sales_by_region(
    service: ReportService = Depends(get_report_service), _: User = Depends(get_current_user)
) -> list[SalesByRegionRow]:
    return service.sales_by_region()


@router.get("/sales/monthly", response_model=list[MonthlyRevenueRow])
def sales_monthly(
    year: int | None = None,
    service: ReportService = Depends(get_report_service),
    _: User = Depends(get_current_user),
) -> list[MonthlyRevenueRow]:
    return service.monthly_revenue(year=year)


@router.get("/inventory/low-stock", response_model=list[LowStockRow])
def low_stock(
    service: ReportService = Depends(get_report_service), _: User = Depends(get_current_user)
) -> list[LowStockRow]:
    return service.low_stock()


@router.get("/inventory/stock-alerts", response_model=list[StockAlertRow])
def stock_alerts(
    limit: int = 10,
    service: ReportService = Depends(get_report_service),
    _: User = Depends(get_current_user),
) -> list[StockAlertRow]:
    return service.stock_alerts(limit=limit)


@router.get("/inventory/stock-health", response_model=list[StockHealthRow])
def stock_health(
    limit: int = 10,
    service: ReportService = Depends(get_report_service),
    _: User = Depends(get_current_user),
) -> list[StockHealthRow]:
    return service.stock_health(limit=limit)


@router.get("/inventory/projections", response_model=list[StockProjectionRow])
def stock_projections(
    service: ReportService = Depends(get_report_service), _: User = Depends(get_current_user)
) -> list[StockProjectionRow]:
    return service.stock_projections()


@router.get("/summary", response_model=SummaryRow)
def summary(
    service: ReportService = Depends(get_report_service), _: User = Depends(get_current_user)
) -> SummaryRow:
    return service.summary()
