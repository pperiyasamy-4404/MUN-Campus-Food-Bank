"""Keyed hashes (HMAC). The same text and the same key always give the same 64 characters.

We use them where we must find something again from what a person types,
without ever saving what they typed: ID numbers (P2), setup codes, the
usernames and numbers that wrong tries are counted under (P9), and trusted
devices.

Why not a plain hash: there are only a billion 9-digit numbers, so anyone could
hash them all and look the answer up. Without the key, nobody can make that list.
"""

import hashlib
import hmac

from app.config import config


def keyed_hash(purpose: str, text: str) -> str:
    """HMAC-SHA256 of the text, as 64 characters of 0-9 and a-f.

    The purpose goes in front, so the same text used for two different things
    gives two different hashes. A setup code that happened to look like a
    username could never match it.
    """
    key = config.secret_key.get_secret_value().encode()
    message = f"{purpose}:{text}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def id_hash(id_number: str) -> str:
    """The only form an ID number is ever saved in (P2). Expects the 9 digits, tidied."""
    return keyed_hash("student-id", id_number)


def username_hash(username: str) -> str:
    """What a staff member's wrong tries are counted under (P9). Capitals don't matter."""
    return keyed_hash("staff-username", username.lower())
