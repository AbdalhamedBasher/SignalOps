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

    # Permitted frontend origins for CORS. Supports comma-separated strings
    # (e.g. "https://signalops.vercel.app,http://localhost:5173") or "*" for demo staging.
    cors_origins: str = "http://localhost:5173"

    # The triage agent's model. Google AI Studio issues a free key with no
    # credit card, and Gemini is on the hackathon's approved provider list.
    # Flash by default: the free tier is generous and a live demo cannot
    # afford to be rate-limited. Swap to gemini-2.5-pro for deeper reasoning.
    google_api_key: str | None = None
    # Measured on real runs, not chosen from a table:
    #
    #   gemini-2.5-flash          404 — retired for new API keys
    #   gemini-3.6-flash          22s, then 92s on the next call
    #   gemini-flash-lite-latest  6.0s and 6.1s, same verdicts
    #
    # The lite model reached the same conclusions on both a four-alarm cascade
    # and a false-alarm case, so the slower model buys nothing here and the
    # variance would be painful in a live demo. Set TRIAGE_MODEL to
    # gemini-3.6-flash if a harder incident ever needs the extra reasoning.
    triage_model: str = "gemini-flash-lite-latest"

    # Nokia Network as Code. Without a key the CAMARA calls run against the
    # deterministic simulator, which is what Nokia recommends for development
    # and what keeps a demo alive when the network is not reachable.
    nokia_api_key: str | None = None
    # The SDK ships with network-as-code.p-eu.rapidapi.com as its default,
    # which returns RapidAPI's own {"message": "API doesn't exists"} for a
    # console-issued key. This is the host those keys actually route
    # through — found by trying them, not documented anywhere we could read.
    nokia_rapidapi_host: str = "network-as-code.nokia.rapidapi.com"
    # A free account runs in Nokia's Simulator mode, where location
    # verification answers TRUE for any coordinates on Earth. Recorded so
    # readings can declare themselves non-discriminating instead of being
    # mistaken for evidence. Set false only with a commercial account.
    nokia_simulator_mode: bool = True

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
    def normalized_database_url(self) -> str:
        """
        Convert legacy cloud postgres schemes to modern SQLAlchemy 2.0 psycopg syntax.

        WHY: Cloud providers such as Render and Railway inject DATABASE_URL using
        the deprecated 'postgres://' dialect scheme. SQLAlchemy 2.0 dropped support
        for this scheme and expects 'postgresql+psycopg://'.
        """
        url = self.database_url.strip()
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://") and not url.startswith("postgresql+"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def is_sqlite(self) -> bool:
        return self.normalized_database_url.startswith("sqlite")

    @property
    def parsed_cors_origins(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
