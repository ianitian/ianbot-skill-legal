from fastapi import FastAPI

from bot.router import router as bot_router
from ingest.routes import router

app = FastAPI(
    title="ianbot-api",
    description="Ingest and sync API for ian-bot-legal (contracts + payments catalog).",
    version="0.0.7",
)

app.include_router(router)
app.include_router(bot_router, prefix="/webhooks", tags=["bot"])
