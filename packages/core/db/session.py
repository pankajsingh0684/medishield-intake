"""Database URL settings and SQLAlchemy session factory."""

from collections.abc import Iterator
from contextlib import contextmanager

from pydantic_settings import SettingsConfigDict
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from packages.core.config import EnvFileSettings


class DatabaseSettings(EnvFileSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    database_url: str


def create_database_engine(database_url: str | None = None) -> Engine:
    url = database_url or DatabaseSettings().database_url
    return create_engine(url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as session, session.begin():
        yield session
