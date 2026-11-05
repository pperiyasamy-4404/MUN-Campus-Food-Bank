"""One-time setup codes, like K7QM-4TXP (R1, R3).

8 characters from 31 letters and digits: about 850 billion possible codes. With
5 tries every 15 minutes (P9), guessing one before it expires is hopeless.
"""

import secrets

from app.security.keyed_hash import keyed_hash

# No 0 or O, and no 1, I or L, so nobody misreads the code from a slip of paper.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LENGTH = 8


def new_setup_code() -> str:
    """A random code, shown in two groups of 4 so it's easy to read out."""
    code = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    return f"{code[:4]}-{code[4:]}"


def tidy_setup_code(typed: str) -> str:
    """'k7qm 4txp' and 'K7QM-4TXP' are the same code."""
    return typed.upper().replace("-", "").replace(" ", "")


def looks_like_a_setup_code(typed: str) -> bool:
    code = tidy_setup_code(typed)
    return len(code) == LENGTH and all(character in ALPHABET for character in code)


def setup_code_hash(code: str) -> str:
    """Only this is saved, never the code (ck_setup_codes_code_hash_looks_like_hmac)."""
    return keyed_hash("setup-code", tidy_setup_code(code))
