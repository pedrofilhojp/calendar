import logging
import os
from dataclasses import dataclass


LOGGER = logging.getLogger("agenda.config")


REQUIRED_ENV = (
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "RABBITMQ_HOST",
    "RABBITMQ_USER",
    "RABBITMQ_PASSWORD",
    "JWT_SECRET",
)


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    rabbitmq_host: str
    rabbitmq_user: str
    rabbitmq_password: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 120

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def rabbitmq_url(self) -> str:
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:5672/%2F"
        )


def load_settings() -> Settings:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        LOGGER.error("Missing required environment variables: %s", ", ".join(missing))
        raise RuntimeError(
            "Backend startup failed. Missing required environment variables: "
            + ", ".join(missing)
        )

    return Settings(
        db_host=os.environ["DB_HOST"],
        db_port=int(os.environ["DB_PORT"]),
        db_name=os.environ["DB_NAME"],
        db_user=os.environ["DB_USER"],
        db_password=os.environ["DB_PASSWORD"],
        rabbitmq_host=os.environ["RABBITMQ_HOST"],
        rabbitmq_user=os.environ["RABBITMQ_USER"],
        rabbitmq_password=os.environ["RABBITMQ_PASSWORD"],
        jwt_secret=os.environ["JWT_SECRET"],
    )


settings = load_settings()
