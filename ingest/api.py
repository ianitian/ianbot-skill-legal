from fastapi import FastAPI

from ingest.routes import router

app = FastAPI(
    title="ianbot-api",
    description="Ingest and sync API for ian-bot-legal (contracts + payments catalog).",
    version="0.0.2",
)

app.include_router(router)
