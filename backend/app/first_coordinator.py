"""Make the first coordinator account, once, when the system is installed (R3).

Run from the backend folder, on the server itself:

    .venv/Scripts/python -m app.first_coordinator Alex

It prints a setup code. The coordinator opens the staff setup page, types the
username and the code, and chooses a password. Nobody else ever sees it.

There is no web page for this on purpose: before the first coordinator exists,
there is nobody who could be trusted to use one. Whoever can run this on the
server can already do anything.

Forgot the password? Run it again with the same username for a new code. It
never makes a second coordinator.
"""

import argparse
import sys

from pydantic import TypeAdapter, ValidationError

from app.db import SessionLocal
from app.deps import get_now
from app.security.inputs import NewUsername
from app.services.accounts import AccountProblem, food_bank_settings, set_up_first_coordinator
from app.services.pickup_days import NEWFOUNDLAND


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Make the first coordinator account, or give it a new setup code.")
    parser.add_argument("username", help="a first name or a nickname, like Alex")
    username_typed = parser.parse_args(arguments).username

    try:
        username = TypeAdapter(NewUsername).validate_python(username_typed)
    except ValidationError as problem:
        print(problem.errors()[0]["msg"], file=sys.stderr)
        return 1

    with SessionLocal() as db:
        try:
            food_bank_settings(db)
        except LookupError:
            print("The food bank settings aren't in the database yet, so a setup code can't be given.", file=sys.stderr)
            return 1
        try:
            issued = set_up_first_coordinator(db, username, get_now())
        except AccountProblem as problem:
            print(problem.message, file=sys.stderr)
            return 1
        db.commit()

    expires = issued.expires_at.astimezone(NEWFOUNDLAND)
    print("Made the coordinator account." if issued.new_account else "Gave the coordinator a new setup code.")
    print(f"  Username:   {username}")
    print(f"  Setup code: {issued.code}")
    print(f"  Runs out:   {expires:%A %d %B %Y, %I:%M %p} (Newfoundland time)")
    print("Open the staff setup page, type the username and the setup code, and choose a password.")
    print("This code is shown only now. Run this again for a new one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
