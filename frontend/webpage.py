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
      img { width: 100%; max-width: 1200px; border: 1px solid #ccc; }
    </style>
  </head>
  <body>
    <h1>Raw Video Feed</h1>
    <img src="/video" />
  </body>
</html>
"""

_BOUNDARY = "frame"


def _b64decode_padded(s: bytes) -> bytes:
    # Base64 strings must be padded to a multiple of 4.
    pad = (-len(s)) % 4
    if pad:
        s += b"=" * pad
    return base64.b64decode(s)


# Placeholder 1x1 JPEG (base64). Padding is handled automatically.
_PLACEHOLDER_JPEG = _b64decode_padded(
    b"/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAALCAABAAEBAREA/8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAVAQEBAAAAAAAAAAAAAAAAAAAABP/aAAwDAQACEAMQAAAByw//xAAXEAADAQAAAAAAAAAAAAAAAAAAAREC/9oACAEBAAEFAlp//8QAFBEBAAAAAAAAAAAAAAAAAAAAEP/aAAgBAwEBPwFH/8QAFBEBAAAAAAAAAAAAAAAAAAAAEP/aAAgBAgEBPwFH/8QAFxABAQEBAAAAAAAAAAAAAAAAAQARIf/aAAgBAQAGPwJvF//8QAFxABAQEBAAAAAAAAAAAAAAAAAQARIf/aAAgBAQABPyG3p//aAAwDAQACEAMQAAAQx//EABcRAQEBAQAAAAAAAAAAAAAAAAEAERL/2gAIAQMBAT8QkV//xAAXEQEBAQEAAAAAAAAAAAAAAAABABEh/9oACAECAQE/EJpG/8QAFxABAQEBAAAAAAAAAAAAAAAAAQARIf/aAAgBAQABPxCk3//Z"
)


def create_app(arenacam):
    logger = get_logger("frontend")
    app = web.Application()

    async def index(request):
        return web.Response(text=HTML, content_type="text/html")

    async def video(request):
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
        logger.info("Web client connected")

        try:
            while True:
                frame = arenacam.latest_frame or _PLACEHOLDER_JPEG

                header = (
                    f"--{_BOUNDARY}\r\n"
                    "Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(frame)}\r\n"
                    "\r\n"
                ).encode("utf-8")

                await resp.write(header)
                await resp.write(frame)
                await resp.write(b"\r\n")

                await asyncio.sleep(0.05)  # ~20 FPS
        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            logger.info("Web client disconnected")

        return resp

    app.router.add_get("/", index)
    app.router.add_get("/video", video)
    return app
