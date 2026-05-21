from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

import tasks.exports
import tasks.reports
import tasks.sweeper  # noqa: F401
from core.middleware import SecurityHeadersMiddleware
from core.ssm import load_into_settings

load_into_settings()
from routes import auth, customers, jobs, orders, pipeline, products, reports, stores  # noqa: E402

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Databridge API",
    description="Multi-source data viewer and reporting API",
    version="0.1.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(customers.router, prefix="/customers", tags=["customers"])
app.include_router(products.router, prefix="/products", tags=["products"])
app.include_router(orders.router, prefix="/orders", tags=["orders"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(stores.router, prefix="/stores", tags=["stores"])
app.include_router(pipeline.router, prefix="/pipeline", tags=["pipeline"])


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
