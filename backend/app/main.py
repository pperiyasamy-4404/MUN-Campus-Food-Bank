import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from app.config import config
from app.door import WaitAtTheDoor
from app.problems import Problem
from app.routes import (
    accounts,
    booking,
    counter,
    days,
    fixes,
    food,
    login,
    packing,
    photos,
    pickup_days,
    settings,
    stock,
    totals,
)
from app.services.accounts import TooManyTries

errors = logging.getLogger("app.errors")


class ErrorLogFile(RotatingFileHandler):
    """A log file that starts a new one at 1 MB, and never drops a line.

    With several server processes, Windows can't rename the file while another
    process has it open. The standard handler then printed "Logging error" and
    lost the line (found by the load test, 13 Nov). This one keeps writing to the
    current file instead, and starts a new one when it can.
    """

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except PermissionError:
            if self.stream is None:
                self.stream = self._open()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """When the server starts: write server errors to a file as well (config.error_log).

    Only for a real server (uvicorn, the demo, the load test). The tests' client
    doesn't start this, so running the tests never writes the file.
    """
    handler = None
    if config.error_log:
        # 1 MB a file, the last 5 kept, so the log can never fill the disk.
        handler = ErrorLogFile(config.error_log, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        errors.addHandler(handler)
    errors.setLevel(logging.ERROR)
    yield
    if handler is not None:
        errors.removeHandler(handler)
        handler.close()


app = FastAPI(title="Campus Food Bank", lifespan=lifespan)

# Every server address starts with /api, so the React dev server can pass
# these on to FastAPI and keep everything else for itself.
app.include_router(pickup_days.router)
app.include_router(food.router)
app.include_router(login.router)
app.include_router(accounts.router)
app.include_router(stock.router)
app.include_router(booking.router)
app.include_router(packing.router)
app.include_router(counter.router)
app.include_router(fixes.router)
app.include_router(photos.router)
app.include_router(days.router)
app.include_router(settings.router)
app.include_router(totals.router)


@app.exception_handler(Problem)
def person_can_fix(request: Request, problem: Problem) -> JSONResponse:
    """Something the person can fix, like a wrong password, in words they can read."""
    headers = {}
    if isinstance(problem, TooManyTries):
        # The standard way to say "wait this many seconds", for the page to count down.
        headers["Retry-After"] = str(problem.retry_after_seconds)
    return JSONResponse({"detail": problem.message}, status_code=problem.status_code, headers=headers)


@app.exception_handler(RequestValidationError)
def form_problem(request: Request, problem: RequestValidationError) -> JSONResponse:
    """What was wrong with a form, like "Enter the 9 digits on your MUN card."

    FastAPI's own answer repeats what was typed ("input"), so a mistyped ID
    number or password would come straight back in the error. This one keeps
    only where the problem is and what it is (P10).
    """
    errors = [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]} for error in problem.errors()]
    return JSONResponse({"detail": errors}, status_code=422)


@app.exception_handler(Exception)
def server_fault(request: Request, error: Exception) -> JSONResponse:
    """A bug or an outage on our side: a 500, in words, and a line in the error log.

    The log gets the address and the error, never the request's body or query,
    so never an ID number or a password (P10). Addresses never hold an ID number.
    The database's error messages leave out the values sent (db.py, hide_parameters).
    """
    errors.error("%s %s failed", request.method, request.url.path, exc_info=error)
    return JSONResponse(
        {"detail": "Something went wrong on our side. Please try again in a minute."}, status_code=500
    )


# FastAPI's own pages about the addresses. Off unless config.api_docs says so.
API_DOCS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}

# Sent with every answer. Each tells the browser to refuse a kind of attack.
SAFETY_HEADERS = {
    # Read a file as the type the server says, never guess (a photo can't turn into a script).
    "X-Content-Type-Options": "nosniff",
    # No other site may show ours inside a frame, so it can't trick someone into clicking.
    "X-Frame-Options": "DENY",
    # Links to other sites don't tell them which of our pages someone came from.
    "Referrer-Policy": "same-origin",
    # The site never uses the camera, microphone, location or payments.
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    # Scripts, styles, photos and requests only from this site; no plugins; no framing.
    # So even if someone got text onto a page, the browser wouldn't run it as a script.
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
}


@app.middleware("http")
async def safety_headers(request: Request, call_next):
    if request.url.path in API_DOCS and not config.api_docs:
        return Response(status_code=404)
    response = await call_next(request)
    for name, value in SAFETY_HEADERS.items():
        # The docs page loads its scripts from a CDN, so it keeps FastAPI's own rules.
        if name == "Content-Security-Policy" and request.url.path in API_DOCS:
            continue
        response.headers.setdefault(name, value)
    if config.cookie_secure:
        # Over https: the browser uses https for this site for a year, even if someone types http.
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response


@app.middleware("http")
async def never_keep_a_copy(request: Request, call_next):
    """Answers can hold setup codes and who is logged in, so no browser or proxy
    may store a copy. Pressing Back after logging out then shows nothing private."""
    response = await call_next(request)
    # Unless the address chose its own, like a photo, which holds nothing private.
    if request.url.path.startswith("/api") and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    return response


# Added last, so it's the outermost layer: a request waits here before anything else runs.
app.add_middleware(WaitAtTheDoor, places=config.db_connections)
