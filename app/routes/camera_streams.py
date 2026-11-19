"""The RTSP camera service, for people signed in. The key stays here, and each account reaches only its own cameras."""

from typing import Annotated, Any, NoReturn
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.dependencies import AuditTrail, CurrentUser, OwnerUser, Visible, get_camera_store, require_camera_manager
from app.schemas.audit import AuditAction
from app.schemas.camera import SavedCamera
from app.schemas.camera_stream import CameraStreamCreate, CameraStreamList, CameraStreamView, host_of
from app.services.camera_manager import CameraManager, CameraManagerError
from app.services.camera_store import CameraNameTakenError, CameraStore

router = APIRouter(tags=["cameras"])
CameraId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]

#: The same cap as saving a camera directly.
MAX_SAVED_CAMERAS = 50


def _fail(error: CameraManagerError) -> NoReturn:
    """What the browser may know. Never a 401: that means the person's session ended, and this is not about them."""
    code = error.status
    if code == 404:
        raise HTTPException(status_code=404, detail="The camera service does not have that camera") from None
    if code == 409:
        raise HTTPException(status_code=409, detail="The camera service is at its limit of cameras") from None
    if code == 422:
        raise HTTPException(status_code=422, detail="The camera service did not accept that address") from None
    if code in (401, 403):
        raise HTTPException(status_code=502, detail="The camera service refused this server's key") from None
    raise HTTPException(status_code=503, detail="The camera service is not responding") from None


def _view(camera_id: str, name: str, reported: dict[str, Any]) -> CameraStreamView:
    """Only what a person needs: the service's error text and internal addresses can hold a password."""
    address, hls, retries, state = (reported.get(key) for key in ("camara", "hls_url", "reintentos", "estado"))
    return CameraStreamView(
        id=camera_id, name=name,
        state=state if isinstance(state, str) else "detenido",
        address=host_of(address) if isinstance(address, str) else None,
        retries=retries if isinstance(retries, int) else 0,
        hls_url=hls if isinstance(hls, str) and hls.startswith(("http://", "https://")) else None,
    )


@router.get("/api/camera-streams", response_model=CameraStreamList)
def list_camera_streams(
    _user: CurrentUser,
    scope: Visible,
    manager: CameraManager = Depends(require_camera_manager),
    store: CameraStore = Depends(get_camera_store),
) -> CameraStreamList:
    """The cameras of this account the service is transmitting. It holds every account's, so this is what filters.

    CurrentUser as well as Visible: without account isolation Visible lets anyone through.
    """
    try:
        reported = manager.list()
    except CameraManagerError as error:
        _fail(error)
    items = []
    for item in reported:
        camera_id = item.get("camara_id")
        saved = store.saved_one(camera_id) if isinstance(camera_id, str) else None
        if saved is not None and scope.sees_account(saved.account_id):
            items.append(_view(saved.id, saved.name, item))
    return CameraStreamList(items=items, total=len(items))


@router.post("/api/camera-streams", response_model=CameraStreamView, status_code=status.HTTP_201_CREATED)
def start_camera_stream(
    data: CameraStreamCreate,
    owner: OwnerUser,
    audit: AuditTrail,
    manager: CameraManager = Depends(require_camera_manager),
    store: CameraStore = Depends(get_camera_store),
) -> CameraStreamView:
    """Transmits the camera with this name, saving it first if the account has none.

    The id comes from here, and alerts need exactly that id, so nobody has to type one or can name another account's.
    """
    wanted = data.name.casefold()
    saved = next((item for item in store.saved(owner.account_id) if item.name.casefold() == wanted), None)
    created = saved is None
    if saved is None:
        if len(store.saved(owner.account_id)) >= MAX_SAVED_CAMERAS:
            raise HTTPException(status_code=409, detail="This account already has too many cameras")
        scheme = data.url.partition(":")[0].lower()
        saved = SavedCamera(
            id=f"cam-{uuid4().hex[:12]}", name=data.name, source=f"{scheme}://{host_of(data.url)}",
            account_id=owner.account_id,
        )
        try:
            store.save(saved)
        except CameraNameTakenError as error:
            raise HTTPException(status_code=409, detail="This account already has a camera with that name") from error
    try:
        reported = manager.configure(saved.id, data.url)
    except CameraManagerError as error:
        # A camera that never connected is not left behind on the Cameras page.
        if created:
            store.forget(saved.id)
        _fail(error)
    if created:
        audit.record(
            AuditAction.CAMERA_SAVED, actor_id=owner.id, actor_email=owner.email,
            target_type="camera", target_id=saved.id, detail={"name": saved.name},
        )
    audit.record(
        AuditAction.CAMERA_STREAM_STARTED, actor_id=owner.id, actor_email=owner.email,
        target_type="camera", target_id=saved.id, detail={"host": host_of(data.url)},
    )
    return _view(saved.id, saved.name, reported)


@router.delete("/api/camera-streams/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def stop_camera_stream(
    camera_id: CameraId,
    owner: OwnerUser,
    audit: AuditTrail,
    scope: Visible,
    manager: CameraManager = Depends(require_camera_manager),
    store: CameraStore = Depends(get_camera_store),
) -> None:
    """Stops transmitting. The camera stays saved in the account."""
    saved = store.saved_one(camera_id)
    if saved is None or not scope.sees_account(saved.account_id):
        raise HTTPException(status_code=404, detail=f"No saved camera with id {camera_id}")
    try:
        manager.remove(camera_id)
    except CameraManagerError as error:
        _fail(error)
    audit.record(
        AuditAction.CAMERA_STREAM_STOPPED, actor_id=owner.id, actor_email=owner.email,
        target_type="camera", target_id=camera_id, detail={"name": saved.name},
    )
