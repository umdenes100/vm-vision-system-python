import asyncio
import base64
from aiohttp import web

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
        <div class="hint">Uses markers 0–3 to define crop. Shows placeholder until all are detected.</div>
      </div>
    </div>
  </body>
</html>
"""

_BOUNDARY = "frame"


def _b64decode_padded(s: bytes) -> bytes:
    pad = (-len(s)) % 4
    if pad:
        s += b"=" * pad
    return base64.b64decode(s)


_PLACEHOLDER_JPEG = _b64decode_padded(
    b"/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAALCAABAAEBAREA/8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAVAQEBAAAAAAAAAAAAAAAAAAAABP/aAAwDAQACEAMQAAAByw//xAAXEAADAQAAAAAAAAAAAAAAAAAAAREC/9oACAEBAAEFAlp//8QAFBEBAAAAAAAAAAAAAAAAAAAAEP/aAAgBAwEBPwFH/8QAFBEBAAAAAAAAAAAAAAAAAAAAEP/aAAgBAgEBPwFH/8QAFxABAQEBAAAAAAAAAAAAAAAAAQARIf/aAAgBAQAGPwJvF//8QAFxABAQEBAAAAAAAAAAAAAAAAAQARIf/aAAgBAQABPyG3p//aAAwDAQACEAMQAAAQx//EABcRAQEBAQAAAAAAAAAAAAAAAAEAERL/2gAIAQMBAT8QkV//xAAXEQEBAQEAAAAAAAAAAAAAAAABABEh/9oACAECAQE/EJpG/8QAFxABAQEBAAAAAAAAAAAAAAAAAQARIf/aAAgBAQABPxCk3//Z"
)


async def _mjpeg_stream(request: web.Request, logger, frame_getter):
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

    return resp


def create_app(arenacam, arena_processor):
    logger = get_logger("frontend")
    app = web.Application()

    async def index(request):
        return web.Response(text=HTML, content_type="text/html")

    async def video(request):
        logger.info("Web client connected to /video")
        resp = await _mjpeg_stream(request, logger, lambda: arenacam.latest_frame)
        logger.info("Web client disconnected from /video")
        return resp

    async def overlay(request):
        logger.info("Web client connected to /overlay")
        resp = await _mjpeg_stream(request, logger, lambda: arena_processor.latest_overlay_jpeg)
        logger.info("Web client disconnected from /overlay")
        return resp

    async def crop(request):
        logger.info("Web client connected to /crop")
        resp = await _mjpeg_stream(request, logger, lambda: arena_processor.latest_cropped_jpeg)
        logger.info("Web client disconnected from /crop")
        return resp

    app.router.add_get("/", index)
    app.router.add_get("/video", video)
    app.router.add_get("/overlay", overlay)
    app.router.add_get("/crop", crop)
    return app
