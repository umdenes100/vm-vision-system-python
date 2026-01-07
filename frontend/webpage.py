import asyncio
from pathlib import Path
from aiohttp import web

from utils.logging import get_logger

_BOUNDARY = "frame"


async def _mjpeg_stream(stop_event: asyncio.Event, request: web.Request, frame_getter):
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
                await asyncio.sleep(0.05)
                continue

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
        # Serve the static index.html
        if not index_path.exists():
            return web.Response(text="Missing frontend/static/index.html", status=500)
        return web.FileResponse(path=index_path)

    # Dynamic endpoints (streams)
    async def video(request):
        logger.info("Web client connected to /video")
        resp = await _mjpeg_stream(stop_event, request, lambda: arenacam.latest_frame)
        logger.info("Web client disconnected from /video")
        return resp

    async def overlay(request):
        logger.info("Web client connected to /overlay")
        resp = await _mjpeg_stream(stop_event, request, lambda: arena_processor.latest_overlay_jpeg)
        logger.info("Web client disconnected from /overlay")
        return resp

    async def crop(request):
        logger.info("Web client connected to /crop")
        resp = await _mjpeg_stream(stop_event, request, lambda: arena_processor.latest_cropped_jpeg)
        logger.info("Web client disconnected from /crop")
        return resp

    # Placeholder websocket endpoint (for future UI interactions)
    async def ws_handler(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        # Placeholder: accept connection, do nothing meaningful yet
        logger.info("WebSocket client connected to /ws (placeholder)")
        try:
            async for _msg in ws:
                # Future: handle messages from UI buttons/dropdowns here
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

    # Static assets served under /static/
    app.router.add_static("/static/", path=static_dir, show_index=False)

    return app
