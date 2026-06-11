import logging

from bot.outbound.slack_client import post_slack_message
from bot.outbound.telegram_client import send_telegram_text
from bot.schemas import BotEvent, BotReply
from core.config import Settings

logger = logging.getLogger(__name__)


def format_debug_message(settings: Settings, event: BotEvent, reply: BotReply) -> str:
    handler = reply.handler or ("forced" if event.forced_reply else "unknown")
    lines = [
        "[won-bot debug]",
        f"platform: {event.platform}",
        f"handler: {handler}",
    ]

    meta = reply.handler_metadata
    if settings.bot_faq_enabled and "fuzzy_threshold" in meta:
        threshold = meta.get("fuzzy_threshold", settings.bot_faq_min_score)
        matched = bool(meta.get("fuzzy_matched"))
        lines.append(f"fuzzy: {'matched' if matched else 'miss'} (threshold {threshold})")
        if reply.handler == "faq":
            if meta.get("faq_id") is not None:
                lines.append(f"faq_id: {meta['faq_id']}")
            if meta.get("score") is not None:
                lines.append(f"score: {meta['score']}")
        fuzzy_top = meta.get("fuzzy_top") or []
        if fuzzy_top:
            lines.append("top candidates:")
            for index, candidate in enumerate(fuzzy_top, start=1):
                lines.append(
                    f"  {index}. {candidate['faq_id']} ({candidate['score']}) — {candidate['question']}"
                )

    return "\n".join(lines)


def emit_debug(settings: Settings, event: BotEvent, text: str) -> None:
    if not settings.bot_debug_enabled:
        return

    if event.platform == "telegram":
        debug_chat_id = (settings.telegram_debug_chat_id or "").strip()
        if debug_chat_id:
            logger.info("Emitting Telegram debug to chat_id=%s", debug_chat_id)
            send_telegram_text(settings, debug_chat_id, text)
        return

    if event.platform != "slack":
        return

    if not settings.bot_slack_configured:
        logger.warning("Slack debug skipped: SLACK_BOT_TOKEN not configured")
        return

    debug_channel = (settings.slack_debug_channel_id or "").strip()
    if debug_channel:
        post_slack_message(settings, debug_channel, text)
        return

    if not event.chat_id or not event.thread_id:
        logger.warning("Slack thread debug skipped: missing channel or thread_id")
        return

    post_slack_message(settings, event.chat_id, text, thread_ts=event.thread_id)
