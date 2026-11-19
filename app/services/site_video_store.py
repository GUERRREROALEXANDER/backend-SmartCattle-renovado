"""The video on the site's cover page.

One row for the whole deployment, not one per account: the cover is what a visitor sees before signing in, so it
belongs to the site. It has nothing to do with the uploaded videos the AI analyses (video_uploads) or with the
cameras' live pictures; it only remembers where the cover's file is served from.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select

from app.db import SessionFactory
from app.models import SiteSettingRow

_KEY = "video_inicio"


@dataclass(frozen=True)
class SiteVideo:
    url: str
    title: str | None
    poster_url: str | None
    updated_at: datetime


def _as_utc(value: datetime) -> datetime:
    # SQLite gives the moment back without its zone; PostgreSQL keeps it.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class SiteVideoStore(Protocol):
    def get(self) -> SiteVideo | None: ...

    def put(self, video: SiteVideo) -> SiteVideo: ...

    def clear(self) -> bool: ...


class InMemorySiteVideoStore:
    def __init__(self) -> None:
        self._video: SiteVideo | None = None

    def get(self) -> SiteVideo | None:
        return self._video

    def put(self, video: SiteVideo) -> SiteVideo:
        self._video = video
        return video

    def clear(self) -> bool:
        had = self._video is not None
        self._video = None
        return had


class SqlSiteVideoStore:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def get(self) -> SiteVideo | None:
        with self._sessions() as session:
            row = session.scalar(select(SiteSettingRow).where(SiteSettingRow.key == _KEY))
            if row is None:
                return None
            try:
                value = json.loads(row.value)
                return SiteVideo(
                    url=str(value["url"]), title=value.get("title"), poster_url=value.get("poster_url"),
                    updated_at=_as_utc(row.updated_at),
                )
            except (ValueError, KeyError, TypeError):
                # A row somebody edited by hand must not take the cover page down with it.
                return None

    def put(self, video: SiteVideo) -> SiteVideo:
        value = json.dumps({"url": video.url, "title": video.title, "poster_url": video.poster_url})
        with self._sessions() as session:
            row = session.get(SiteSettingRow, _KEY)
            if row is None:
                session.add(SiteSettingRow(key=_KEY, value=value, updated_at=video.updated_at))
            else:
                row.value = value
                row.updated_at = video.updated_at
            session.commit()
        return video

    def clear(self) -> bool:
        with self._sessions() as session:
            row = session.get(SiteSettingRow, _KEY)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
