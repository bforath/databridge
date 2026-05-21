from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    All configuration comes from environment variables.
    Pydantic reads them automatically — no manual os.getenv() calls needed.

    In Docker, these are set in docker-compose.yml under `environment:`.
    Locally, you can put them in a .env file and pydantic reads that too.
    """

    database_url: str
    secret_key: str
    redis_url: str
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    mail_from: str = "databridge@localhost"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # S3 — bucket name and optional LocalStack override
    s3_bucket: str = "databridge-exports"
    s3_export_expiry: int = 86400  # pre-signed URL TTL in seconds (24 h)
    aws_endpoint_url: str = ""       # internal Docker endpoint for uploads (http://localstack:4566 in dev)
    s3_public_url: str = ""          # browser-reachable endpoint for pre-signed URLs (http://localhost:4566 in dev)

    class Config:
        env_file = ".env"  # optional local override, ignored if file doesn't exist


# Single shared instance — import this anywhere you need config
settings = Settings()
