from pathlib import Path

from pydantic import SecretStr
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
    # The key for every keyed hash (HMAC). It lives here, outside the database, so
    # a stolen copy of the database can't be turned back into ID numbers (P2).
    # SecretStr keeps it out of error messages and logs. Back it up (P11).
    secret_key: SecretStr
    # Login cookies are only sent over https. Browsers count localhost as safe,
    # so this stays on while we work. Turn it off only to try the site from a
    # phone on the home network, which uses plain http.
    cookie_secure: bool = True
    # Database connections for each server process, and so how many requests it
    # works on at once (app/door.py). The cloud database must allow this many for
    # every server process, plus a few for the jobs script.
    db_connections: int = 15


config = Config()
