from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Config(BaseSettings):
    """Values that change from one computer to another, read from backend/.env.

    Not to be confused with the food bank's settings (pickup gap, item limit...),
    which live in the database so the coordinator can change them.
    """

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str
    test_database_url: str


config = Config()
