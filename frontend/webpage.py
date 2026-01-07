import asyncio
from aiohttp import web

import cv2
import numpy as np

from utils.logging import get_logger

HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>VM Vision System</title>
    <style>
      body { font-family: sans-serif; margin: 20px; }
      .row { display: flex; gap: 20px; flex-wrap: wrap; }
      .panel { flex: 1; min-width: 420px; }
      img { width: 100%; border: 1px solid #ccc; }
      h2 { margin: 10px 0; font-size: 18px; }
      .hint { color: #666; font-size: 13px; margin-top: 6px; }
    </style>
  </head>
  <body>
    <h1>Vision System Streams</h1>

    <div class="row">
      <div class="panel">
        <h2>Raw</h2>
        <img src="/video" />
      </div>

      <div class="panel">
        <h2>Raw + ArUco Boxes</h2>
        <img src="/overlay" />
        <div class="hint">Green boxes drawn around detected markers.</div>
      </div>
    </div>

    <div class="row" style="margin-top: 20px;">
      <div class="panel">
        <h2>Cropped Arena</h2>
        <img src="/crop" />
        <div class="hint">Crop transform refreshes every 10 minutes; crop persists through marker blinks.</div>
      </div>
    </div>
  </body>
</html>
"""

_BOUNDARY = "frame"


def _make_placeholder_jpeg() -> bytes:
    img = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.putText(
        img,
        "Waiting for crop transform...",
        (10, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    return buf.tobytes() if ok else b""


_PLACEHOLDER_JPEG = _make_placeholder_jpeg()


async def _mjpeg_stream(request: web.Request, frame_getter):
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
        while True:
            frame = frame_getter() or _PLACEHOLDER_JPEG

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


def create_app(arenacam, arena_processor):
    logger = get_logger("frontend")
    app = web.Application()

    async def index(request):
        return web.Response(text=HTML, content_type="text/html")

    async def video(request):
        logger.info("Web client connected to /video")
        resp = await _mjpeg_stream(request, lambda: arenacam.latest_frame)
        logger.info("Web client disconnected from /video")
        return resp

    async def overlay(request):
        logger.info("Web client connected to /overlay")
        resp = await _mjpeg_stream(request, lambda: arena_processor.latest_overlay_jpeg)
        logger.info("Web client disconnected from /overlay")
        return resp

    async def crop(request):
        logger.info("Web client connected to /crop")
        resp = await _mjpeg_stream(request, lambda: arena_processor.latest_cropped_jpeg)
        logger.info("Web client disconnected from /crop")
        return resp

    app.router.add_get("/", index)
    app.router.add_get("/video", video)
    app.router.add_get("/overlay", overlay)
    app.router.add_get("/crop", crop)
    return app
