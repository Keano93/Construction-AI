import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth, projects, review
from .config import get_settings

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Notice API", version="0.1.0",
              description="AI commercial assistant for contractors. Agents draft, humans approve.")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins.split(","), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
for r in (auth.router, projects.router, review.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}
