from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.time_window import DEFAULT_TIME_ZONE


class AssistantTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)


class AssistantQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=500)
    history: list[AssistantTurn] = Field(default_factory=list, max_length=12)
    time_zone: str = Field(default=DEFAULT_TIME_ZONE, max_length=64, description="IANA time zone the days are cut in")


class AssistantReply(BaseModel):
    reply: str
