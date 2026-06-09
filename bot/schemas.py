from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

BotPlatform = Literal["slack", "telegram"]
BotEventType = Literal["message", "action", "url_verification"]


class BotEvent(BaseModel):
    platform: BotPlatform
    event_type: BotEventType
    event_id: str
    user_id: str = ""
    user_name: str = ""
    chat_id: str = ""
    text: Optional[str] = None
    action_id: Optional[str] = None
    challenge: Optional[str] = None
    thread_id: Optional[str] = None
    forced_reply: Optional[str] = None
    raw: dict[str, Any] = Field(default_factory=dict)


BotHandler = Literal["echo", "faq", "fallback"]


class BotReply(BaseModel):
    text: str
    citations: list[str] = Field(default_factory=list)
    ephemeral: bool = False
    handler: Optional[BotHandler] = None
    handler_metadata: dict[str, Any] = Field(default_factory=dict)
