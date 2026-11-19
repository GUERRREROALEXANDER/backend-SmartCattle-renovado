import re
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

_RTSP = re.compile(r"^rtsps?://[^\s/?#]+[^\s]*$", re.IGNORECASE)


class CameraStreamCreate(BaseModel):
    """A camera to transmit. The URL holds its password, so it is passed on and never stored, logged or returned."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80, description="A saved camera's name, or the name for a new one")
    url: str = Field(min_length=1, max_length=500, repr=False, description="rtsp:// or rtsps:// address of the camera")

    @field_validator("name", "url", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("url")
    @classmethod
    def is_rtsp(cls, value: str) -> str:
        if not _RTSP.match(value):
            raise ValueError("url must be the RTSP address of a camera")
        # An "@" past the host is a password with a symbol in it, which would be read as the camera's path.
        parts = urlsplit(value)
        if "@" in parts.path or "@" in parts.query:
            raise ValueError("symbols in the password must be percent-encoded")
        return value


def host_of(url: str) -> str:
    """Only where the camera is. Some cameras take the password in the path or the query, so those never travel on."""
    return urlsplit(url).netloc.rpartition("@")[2]


class CameraStreamView(BaseModel):
    id: str
    name: str
    state: str = Field(description="sin_configurar, conectando, transmitiendo, reconectando or detenido")
    address: str | None = Field(description="Host and port of the camera, with nothing else of its URL")
    retries: int
    hls_url: str | None = Field(description="Where the video plays, on the machine running the camera service")


class CameraStreamList(BaseModel):
    items: list[CameraStreamView]
    total: int
