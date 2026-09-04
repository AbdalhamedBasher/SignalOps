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

    # Off by default: generated briefings call a paid API and the rest of the
    # product works without them. Enabling is an explicit decision, not
    # something that switches itself on because a key happens to be present.
    enable_briefings: bool = False
    briefing_model: str = "claude-opus-5"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
