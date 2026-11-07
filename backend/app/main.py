from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routes import accounts, booking, counter, food, login, packing, photos, pickup_days, stock
from app.problems import Problem
from app.services.accounts import TooManyTries

app = FastAPI(title="Campus Food Bank")

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
app.include_router(photos.router)


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


@app.middleware("http")
async def never_keep_a_copy(request: Request, call_next):
    """Answers can hold setup codes and who is logged in, so no browser or proxy
    may store a copy. Pressing Back after logging out then shows nothing private."""
    response = await call_next(request)
    # Unless the address chose its own, like a photo, which holds nothing private.
    if request.url.path.startswith("/api") and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    return response
