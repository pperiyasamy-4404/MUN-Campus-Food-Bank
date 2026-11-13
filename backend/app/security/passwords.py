"""Password hashes, with argon2 (P8).

argon2 is slow on purpose and needs 64 MB of memory for every guess. Checking
one password takes about a tenth of a second. Trying millions takes far too long.
It also mixes a random salt into each hash, so two students with the same
password get different hashes.
"""

import threading

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# argon2id with the library's settings: 3 passes over 64 MB, 4 lanes.
_hasher = PasswordHasher()

# At most 4 password checks at the same moment in each server process. In the
# load test, 300 students logging in at once made the server use over 1 GB,
# 64 MB for each check running, enough to crash a small cloud server. With 4,
# the checks need at most 256 MB, and logging in is no slower: argon2 is limited
# by the memory's speed, so 15 checks at once each take about 4 times as long.
_at_once = threading.BoundedSemaphore(4)

# A real hash of a password no account has. When nobody has the number that was
# typed, we still check the password against this, so a wrong number takes as long
# to answer as a wrong password. The time never tells which numbers have accounts.
_NO_ACCOUNT = _hasher.hash("nobody has this password")


def hash_password(password: str) -> str:
    """Looks like $argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>."""
    with _at_once:
        return _hasher.hash(password)


def password_matches(password_hash: str | None, password: str) -> bool:
    """True only if there is a password and this is it. Never raises."""
    try:
        with _at_once:
            matches = _hasher.verify(password_hash or _NO_ACCOUNT, password)
    except (VerificationError, InvalidHashError):
        return False
    return matches and password_hash is not None


def needs_new_hash(password_hash: str) -> bool:
    """True if the hash was made with older, weaker settings than we use now."""
    return _hasher.check_needs_rehash(password_hash)
