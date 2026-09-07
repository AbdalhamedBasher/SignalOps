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

    # The triage agent's model. Google AI Studio issues a free key with no
    # credit card, and Gemini is on the hackathon's approved provider list.
    # Flash by default: the free tier is generous and a live demo cannot
    # afford to be rate-limited. Swap to gemini-2.5-pro for deeper reasoning.
    google_api_key: str | None = None
    triage_model: str = "gemini-2.5-flash"

    # Nokia Network as Code. Without a key the CAMARA calls run against the
    # deterministic simulator, which is what Nokia recommends for development
    # and what keeps a demo alive when the network is not reachable.
    nokia_api_key: str | None = None
    nokia_base_url: str = "https://network-as-code.p-eu.rapidapi.com"

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
