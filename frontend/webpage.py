import asyncio
from pathlib import Path
from aiohttp import web

import cv2
import numpy as np

from utils.logging import get_logger

_BOUNDARY = "frame"


def _make_placeholder_jpeg(text: str) -> bytes:
    """
    Guaranteed-valid JPEG placeholder so MJPEG endpoints never stall.
    """
    img = np.zeros((240, 480, 3), dtype=np.uint8)
    cv2.putText(
        img,
        text,
        (12, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    return buf.tobytes() if ok else b""


_PLACEHOLDER_RAW = _make_placeholder_jpeg("Waiting for raw video...")
_PLACEHOLDER_OVERLAY = _make_placeholder_jpeg("Waiting for overlay...")
_PLACEHOLDER_CROP = _make_placeholder_jpeg("Waiting for crop transform...")


async def _mjpeg_stream(
    stop_event: asyncio.Event,
    request: web.Request,
    frame_getter,
    placeholder: bytes,
):
    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": f"multipart/x-mixed-replace; boundary={_BOUNDARY}",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
    await resp.prepare(request)

    try:
        while not stop_event.is_set():
            frame = frame_getter()
            if frame is None:
                frame = placeholder

            header = (
                f"--{_BOUNDARY}\r\n"
                "Content-Type: image/jpeg\r\n"
                f"Content-Length: {len(frame)}\r\n"
                "\r\n"
            ).encode("utf-8")

            await resp.write(header)
            await resp.write(frame)
            await resp.write(b"\r\n")

            await asyncio.sleep(0.05)
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        pass
    finally:
        try:
            await resp.write_eof()
        except Exception:
            pass

    return resp


def create_app(stop_event: asyncio.Event, arenacam, arena_processor):
    logger = get_logger("frontend")
    app = web.Application()

    static_dir = Path(__file__).parent / "static"
    index_path = static_dir / "index.html"

    async def index(request: web.Request) -> web.Response:
        if not index_path.exists():
            return web.Response(text="Missing frontend/static/index.html", status=500)
        return web.FileResponse(path=index_path)

    async def video(request):
        logger.info("Web client connected to /video")
        resp = await _mjpeg_stream(stop_event, request, lambda: arenacam.latest_frame, _PLACEHOLDER_RAW)
        logger.info("Web client disconnected from /video")
        return resp

    async def overlay(request):
        logger.info("Web client connected to /overlay")
        resp = await _mjpeg_stream(stop_event, request, lambda: arena_processor.latest_overlay_jpeg, _PLACEHOLDER_OVERLAY)
        logger.info("Web client disconnected from /overlay")
        return resp

    async def crop(request):
        logger.info("Web client connected to /crop")
        resp = await _mjpeg_stream(stop_event, request, lambda: arena_processor.latest_cropped_jpeg, _PLACEHOLDER_CROP)
        logger.info("Web client disconnected from /crop")
        return resp

    async def ws_handler(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        logger.info("WebSocket client connected to /ws (placeholder)")
        try:
            async for _msg in ws:
                await ws.send_json({"type": "placeholder", "ok": True})
        except Exception:
            pass
        finally:
            logger.info("WebSocket client disconnected from /ws (placeholder)")
        return ws

    app.router.add_get("/", index)
    app.router.add_get("/video", video)
    app.router.add_get("/overlay", overlay)
    app.router.add_get("/crop", crop)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static/", path=static_dir, show_index=False)

    return app
