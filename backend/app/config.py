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

    # No default. A shipped default signing secret is the same as no
    # authentication at all, because anyone who has read the source can mint a
    # supervisor token. When this is unset the application generates a random
    # one at startup and says so: tokens then stop working across restarts,
    # which is inconvenient in development and fatal to nobody in production.
    jwt_secret: str | None = None

    # Seed logins, for development and the demo. Ignored once real users exist.
    seed_engineer_password: str = "engineer-dev-password"
    seed_supervisor_password: str = "supervisor-dev-password"
    seed_collector_password: str = "collector-dev-password"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
