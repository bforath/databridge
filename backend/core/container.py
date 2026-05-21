"""
Service bindings — the single place to swap implementations.

Equivalent to Laravel's AppServiceProvider::register(). Each function
is a FastAPI dependency: routes declare what they need via Depends(),
and this module decides which concrete class they get.

    # To switch the export writer to plain text:
    def get_export_writer() -> WriterProtocol:
        return TextWriter()

    # To switch all repositories to a different database:
    def get_customer_repo(db: Session = Depends(get_db)) -> CustomerRepositoryProtocol:
        return MongoCustomerRepository(db)
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from core.database import get_db
from mailers.interfaces.mailer import MailerProtocol
from mailers.smtp import SmtpMailer
from repositories.interfaces.connection import DataConnectionProtocol
from repositories.interfaces.customer import CustomerRepositoryProtocol
from repositories.interfaces.job import JobRepositoryProtocol
from repositories.interfaces.order import OrderRepositoryProtocol
from repositories.interfaces.pipeline import PipelineRepositoryProtocol
from repositories.interfaces.product import ProductRepositoryProtocol
from repositories.interfaces.reports import ReportsRepositoryProtocol
from repositories.interfaces.store import StoreRepositoryProtocol
from repositories.interfaces.user import UserRepositoryProtocol
from repositories.postgres.customer import PostgresCustomerRepository
from repositories.postgres.customer_table import (
    CustomerRow as _CustomerRow,  # noqa: F401 — registers with SQLAlchemy mapper
)
from repositories.postgres.job import PostgresJobRepository
from repositories.postgres.order import PostgresOrderRepository
from repositories.postgres.pipeline import PostgresPipelineRepository
from repositories.postgres.product import PostgresProductRepository
from repositories.postgres.reports import PostgresReportsRepository
from repositories.postgres.store import PostgresStoreRepository
from repositories.postgres.user import PostgresUserRepository
from repositories.sqlalchemy.connection import SQLAlchemyConnection
from services.auth_service import AuthService
from services.customer_service import CustomerService
from services.job_service import JobService
from services.order_service import OrderService
from services.pipeline_service import PipelineService
from services.product_service import ProductService
from services.report_service import ReportService
from services.store_service import StoreService
from writers.excel import ExcelWriter
from writers.interfaces.writer import WriterProtocol

# ── Infrastructure ────────────────────────────────────────────────────────────

def get_export_writer() -> WriterProtocol:
    return ExcelWriter()


def get_mailer() -> MailerProtocol:
    return SmtpMailer()


# ── Repositories (outbound adapters) ─────────────────────────────────────────

def get_connection(db: Session = Depends(get_db)) -> DataConnectionProtocol:
    # Swap this one line to change the ORM across the entire customer resource.
    return SQLAlchemyConnection(db)


def get_customer_repo(conn: DataConnectionProtocol = Depends(get_connection)) -> CustomerRepositoryProtocol:
    return PostgresCustomerRepository(conn)


def get_product_repo(db: Session = Depends(get_db)) -> ProductRepositoryProtocol:
    return PostgresProductRepository(db)


def get_order_repo(db: Session = Depends(get_db)) -> OrderRepositoryProtocol:
    return PostgresOrderRepository(db)


def get_reports_repo(db: Session = Depends(get_db)) -> ReportsRepositoryProtocol:
    return PostgresReportsRepository(db)


def get_job_repo(db: Session = Depends(get_db)) -> JobRepositoryProtocol:
    return PostgresJobRepository(db)


def get_store_repo(db: Session = Depends(get_db)) -> StoreRepositoryProtocol:
    return PostgresStoreRepository(db)


def get_user_repo(db: Session = Depends(get_db)) -> UserRepositoryProtocol:
    return PostgresUserRepository(db)


def get_pipeline_repo(db: Session = Depends(get_db)) -> PipelineRepositoryProtocol:
    return PostgresPipelineRepository(db)


# ── Services (application layer) ─────────────────────────────────────────────

def get_auth_service(repo: UserRepositoryProtocol = Depends(get_user_repo)) -> AuthService:
    return AuthService(repo)


def get_customer_service(repo: CustomerRepositoryProtocol = Depends(get_customer_repo)) -> CustomerService:
    return CustomerService(repo)


def get_product_service(repo: ProductRepositoryProtocol = Depends(get_product_repo)) -> ProductService:
    return ProductService(repo)


def get_order_service(repo: OrderRepositoryProtocol = Depends(get_order_repo)) -> OrderService:
    return OrderService(repo)


def get_store_service(repo: StoreRepositoryProtocol = Depends(get_store_repo)) -> StoreService:
    return StoreService(repo)


def get_job_service(
    repo: JobRepositoryProtocol = Depends(get_job_repo),
    writer: WriterProtocol = Depends(get_export_writer),
) -> JobService:
    return JobService(repo, writer)


def get_report_service(repo: ReportsRepositoryProtocol = Depends(get_reports_repo)) -> ReportService:
    return ReportService(repo)


def get_pipeline_service(repo: PipelineRepositoryProtocol = Depends(get_pipeline_repo)) -> PipelineService:
    return PipelineService(repo)


# ── Non-DI helpers (Celery tasks, scripts) ────────────────────────────────────

def make_customer_repo(db: Session) -> CustomerRepositoryProtocol:
    """For use outside FastAPI DI (e.g. Celery tasks) where Depends() doesn't run."""
    return PostgresCustomerRepository(SQLAlchemyConnection(db))
