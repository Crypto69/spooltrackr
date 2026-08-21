"""Runtime configuration. Everything can be overridden with env vars."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPOOL_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://spool:spool@localhost:5433/spooltrackr"
    data_dir: Path = Path("./data")
    frontend_dist: Path = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    seed_dir: Path = Path(__file__).resolve().parent.parent / "seed"

    # Printer defaults — the DB `settings` row overrides these once saved in the UI.
    printer_mode: str = "mock"  # mock | live | off
    printer_host: str = ""
    printer_serial: str = ""
    printer_access_code: str = ""

    build_sha: str = "dev"
    build_time: str = "dev"
    log_level: str = "INFO"


settings = Settings()
