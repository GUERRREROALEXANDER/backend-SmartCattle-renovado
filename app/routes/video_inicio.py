"""The cover page's video: which file the site's landing page plays.

Kept apart from /api/videos (analyses of uploaded recordings) and from the cameras' live pictures on purpose: this
is one address for the whole site, public to read, and only a site administrator changes it.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.config import Settings
from app.dependencies import Clock, CurrentUser, get_app_settings, get_clock
from app.schemas.auth import UserRole
from app.schemas.video_inicio import (
    VIDEO_EXTENSIONS,
    VideoInicio,
    VideoInicioIn,
    VideoInicioPermission,
    VideoInicioResponse,
    clean_media_url,
)
from app.services.site_video_store import SiteVideo, SiteVideoStore
from app.services.user_store import StoredUser

router = APIRouter(prefix="/api/video-inicio", tags=["video-inicio"])


def get_site_video_store(request: Request) -> SiteVideoStore:
    store: SiteVideoStore = request.app.state.site_video_store
    return store


def is_site_admin(user: StoredUser, settings: Settings) -> bool:
    """Who may change what every visitor sees before signing in.

    With open registration anybody can become the owner of an account, so being an owner is not enough: the
    deployment names its administrators. Where registration is closed, the owners are people the site trusts.
    """
    if user.role is not UserRole.OWNER:
        return False
    admins = settings.site_admins
    if admins:
        return user.email.lower() in admins
    return not settings.public_registration


def require_site_admin(user: CurrentUser, settings: Settings = Depends(get_app_settings)) -> StoredUser:
    if not is_site_admin(user, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a site administrator can change the cover video (SITE_ADMIN_EMAILS)",
        )
    return user


def _deployment_default(settings: Settings) -> VideoInicio | None:
    if not settings.video_inicio_url:
        return None
    try:
        url = clean_media_url(settings.video_inicio_url, VIDEO_EXTENSIONS, "video")
    except ValueError:
        # A mistyped variable must not break the cover: it falls back to the 3D scene.
        return None
    return VideoInicio(url=url, source="deployment")


@router.get("", response_model=VideoInicioResponse)
def read_video_inicio(
    response: Response,
    store: SiteVideoStore = Depends(get_site_video_store),
    settings: Settings = Depends(get_app_settings),
) -> VideoInicioResponse:
    # Every visitor asks for this; a minute of caching spares the database without making a change feel stuck.
    response.headers["Cache-Control"] = "public, max-age=60"
    stored = store.get()
    if stored is not None:
        return VideoInicioResponse(video=VideoInicio(
            url=stored.url, title=stored.title, poster_url=stored.poster_url, updated_at=stored.updated_at,
            source="panel",
        ))
    return VideoInicioResponse(video=_deployment_default(settings))


@router.get("/permiso", response_model=VideoInicioPermission)
def read_permission(user: CurrentUser, settings: Settings = Depends(get_app_settings)) -> VideoInicioPermission:
    return VideoInicioPermission(can_edit=is_site_admin(user, settings))


@router.put("", response_model=VideoInicioResponse)
def replace_video_inicio(
    body: VideoInicioIn,
    _admin: StoredUser = Depends(require_site_admin),
    store: SiteVideoStore = Depends(get_site_video_store),
    clock: Clock = Depends(get_clock),
) -> VideoInicioResponse:
    saved = store.put(SiteVideo(url=body.url, title=body.title, poster_url=body.poster_url, updated_at=clock()))
    return VideoInicioResponse(video=VideoInicio(
        url=saved.url, title=saved.title, poster_url=saved.poster_url, updated_at=saved.updated_at, source="panel",
    ))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def remove_video_inicio(
    _admin: StoredUser = Depends(require_site_admin),
    store: SiteVideoStore = Depends(get_site_video_store),
) -> Response:
    store.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
