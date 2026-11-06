"""The shapes of what people type: ID numbers, passwords, setup codes and usernames.

ID numbers, passwords and setup codes are SecretStr. If one is ever printed or
logged by mistake it shows as '**********', never the real thing (P3, P10).
"""

import re
from typing import Annotated

from pydantic import AfterValidator, Field, SecretStr
from pydantic_core import PydanticCustomError

from app.security.setup_codes import looks_like_a_setup_code, tidy_setup_code

PASSWORD_MIN = 8
PASSWORD_MAX = 128
USERNAME_MAX = 30


def _tidy_id_number(typed: SecretStr) -> SecretStr:
    """'2023 12345' and '202312345' are the same card. Only the 9 digits are kept."""
    digits = re.sub(r"[\s-]", "", typed.get_secret_value())
    if not re.fullmatch(r"[0-9]{9}", digits):
        raise PydanticCustomError("id_number", "Enter the 9 digits on your MUN card.")
    return SecretStr(digits)


def _not_too_long(password: SecretStr) -> SecretStr:
    """A limit, so nobody can make the server hash a whole book."""
    if len(password.get_secret_value()) > PASSWORD_MAX:
        raise PydanticCustomError("password", f"A password can be at most {PASSWORD_MAX} characters.")
    return password


def _good_new_password(password: SecretStr) -> SecretStr:
    """At least 8 characters, and nothing else: no rules about digits or capitals.

    Rules like "one capital and one symbol" lead to Password1!, which is easy to
    guess. Length is what counts, and a short phrase is easy to remember.
    """
    if len(password.get_secret_value()) < PASSWORD_MIN:
        raise PydanticCustomError("password", f"Choose a password of at least {PASSWORD_MIN} characters.")
    return _not_too_long(password)


def _tidy_setup_code(typed: SecretStr) -> SecretStr:
    if not looks_like_a_setup_code(typed.get_secret_value()):
        raise PydanticCustomError("setup_code", "Enter the 8-character setup code, like K7QM-4TXP.")
    return SecretStr(tidy_setup_code(typed.get_secret_value()))


def _tidy_username(typed: str) -> str:
    """A first name or a nickname (P3). Extra spaces are dropped."""
    username = " ".join(typed.split())
    if not 1 <= len(username) <= USERNAME_MAX or not re.fullmatch(r"[\w .'-]+", username):
        raise PydanticCustomError(
            "username", f"Use up to {USERNAME_MAX} letters, numbers, spaces, dots or dashes."
        )
    return username


IdNumber = Annotated[SecretStr, AfterValidator(_tidy_id_number)]
Password = Annotated[SecretStr, AfterValidator(_not_too_long)]
NewPassword = Annotated[SecretStr, AfterValidator(_good_new_password)]
SetupCode = Annotated[SecretStr, AfterValidator(_tidy_setup_code)]
NewUsername = Annotated[str, AfterValidator(_tidy_username)]
# Logging in only needs a limit: a username that doesn't exist is simply wrong.
Username = Annotated[str, Field(max_length=100), AfterValidator(lambda typed: " ".join(typed.split()))]
