"""Application settings, read from the environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite by default so the project runs with nothing installed. The schema
    # and every query are written to be portable, so moving to PostgreSQL is a
    # change to this one value plus running the same Alembic migrations:
    #
    #   DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/signalops
    database_url: str = "sqlite:///./signalops.db"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
