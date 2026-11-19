from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

VIDEO_EXTENSIONS = (".mp4", ".webm")
POSTER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".avif")
_LOCAL_HOSTS = {"localhost", "127.0.0.1"}


def clean_media_url(value: str, extensions: tuple[str, ...], what: str) -> str:
    """An address a browser can load the file from: https, this computer, or a path on the site itself.

    Nothing else is accepted because the value ends up in the `src` of a tag on the public cover page.
    """
    url = value.strip()
    if any(character.isspace() or character in "\"'<>\\" for character in url):
        raise ValueError(f"The {what} address has characters that are not allowed")
    parts = urlsplit(url)
    if parts.scheme == "" and parts.netloc == "":
        # A file published with the site, such as /video-inicio.mp4.
        if not url.startswith("/") or url.startswith("//"):
            raise ValueError(f"The {what} address must be https://... or a path on the site that starts with /")
    elif parts.scheme == "https":
        if not parts.hostname:
            raise ValueError(f"The {what} address has no host")
    elif parts.scheme == "http":
        if parts.hostname not in _LOCAL_HOSTS:
            raise ValueError(f"The {what} address must use https; http is only accepted for localhost")
    else:
        raise ValueError(f"The {what} address must be https://... or a path on the site that starts with /")
    if not parts.path.lower().endswith(extensions):
        raise ValueError(f"The {what} must be one of: {', '.join(extensions)}")
    return url


class VideoInicioIn(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    title: str | None = Field(default=None, max_length=120)
    poster_url: str | None = Field(default=None, max_length=500)

    @field_validator("url")
    @classmethod
    def video_address(cls, value: str) -> str:
        return clean_media_url(value, VIDEO_EXTENSIONS, "video")

    @field_validator("poster_url")
    @classmethod
    def poster_address(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return clean_media_url(value, POSTER_EXTENSIONS, "poster")

    @field_validator("title")
    @classmethod
    def tidy_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        title = " ".join(value.split())
        return title or None


class VideoInicio(BaseModel):
    url: str
    title: str | None = None
    poster_url: str | None = None
    # None when the address comes from the deployment's VIDEO_INICIO_URL and nobody has replaced it.
    updated_at: datetime | None = None
    #: "panel" when an administrator set it, "deployment" when it is the configured default.
    source: str


class VideoInicioResponse(BaseModel):
    #: None means the cover page shows its own 3D scene.
    video: VideoInicio | None


class VideoInicioPermission(BaseModel):
    can_edit: bool
