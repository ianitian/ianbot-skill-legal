import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from bot.router import router as bot_router
from bot.telegram_polling import start_polling, stop_polling
from ingest.routes import router

logging.basicConfig(level=logging.INFO)
logging.getLogger("bot").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_polling()
    yield
    await stop_polling()


app = FastAPI(
    title="ianbot-api",
    description="Ingest and sync API for ian-bot-legal (contracts + payments catalog).",
    version="0.1.2",
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(bot_router, prefix="/webhooks", tags=["bot"])
