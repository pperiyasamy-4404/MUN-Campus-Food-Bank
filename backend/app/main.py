from fastapi import FastAPI

from app.routes import food, pickup_days

app = FastAPI(title="Campus Food Bank")

# Every server address starts with /api, so the React dev server can pass
# these on to FastAPI and keep everything else for itself.
app.include_router(pickup_days.router)
app.include_router(food.router)
