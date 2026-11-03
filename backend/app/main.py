from fastapi import FastAPI

app = FastAPI(title="Campus Food Bank")


# Every server address starts with /api, so the React dev server can pass
# these on to FastAPI and keep everything else for itself.
@app.get("/api/hello")
def hello():
    return {"message": "Hello from the Campus Food Bank server"}
