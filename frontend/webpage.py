import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from aiohttp import web, WSMsgType

from utils.logging import get_logger, register_web_event_sink


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def _decode_jpeg(jpeg_bytes: bytes) -> Optional[np.ndarray]:
    if not jpeg_bytes:
        return None
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _encode_jpeg(frame: np.ndarray, quality: int = 80) -> Optional[bytes]:
    ok, buf = cv2.imencode(
        ".jpg",
        frame,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)],
    )
    return buf.tobytes() if ok else None


def _draw_waiting_overlay(frame: np.ndarray) -> np.ndarray:
    out = frame.copy()

    text = "Waiting for crop transform..."
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 1.0
    thickness = 2

    h, w = out.shape[:2]
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)

    x = max(10, (w - tw) // 2)
    y = max(th + 10, (h + th) // 2)

    cv2.putText(
        out,
        text,
        (x, y),
        font,
        scale,
        (0, 0, 0),
        thickness + 4,
        cv2.LINE_AA,
    )

    cv2.putText(
        out,
        text,
        (x, y),
        font,
        scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )

    return out


async def _restart_process_after_delay(delay_seconds: float = 0.5):
    await asyncio.sleep(delay_seconds)
    python = sys.executable
    argv = [python] + sys.argv
    os.execv(python, argv)


class WebPage:
    def __init__(self, stop_event, arenacam, arena_processor, restart_password: str = ""):
        self.logger = get_logger("frontend")

        self.stop_event = stop_event
        self.arenacam = arenacam
        self.arena = arena_processor
        self.restart_password = restart_password or ""

        self.app = web.Application()
        self.ws_clients = set()

        self.setup_routes()
        self.setup_event_sink()

    def setup_routes(self):
        self.app.router.add_get("/", self.handle_index)

        self.app.router.add_get("/video", self.handle_video_stream)
        self.app.router.add_get("/overlay", self.handle_overlay_stream)
        self.app.router.add_get("/crop", self.handle_crop_stream)

        self.app.router.add_get("/ws", self.handle_ws)

        self.app.router.add_post("/api/randomize", self.handle_randomize)
        self.app.router.add_post("/api/restart", self.handle_restart)

        self.app.router.add_static(
            "/static/",
            path=str(STATIC_DIR),
            name="static",
            show_index=False,
        )

    def setup_event_sink(self):
        loop = asyncio.get_running_loop()

        def sink(evt):
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.broadcast_event(evt))
            )

        register_web_event_sink(sink)

    async def broadcast_event(self, evt):
        if not self.ws_clients:
            return

        data = json.dumps(evt)

        dead = []
        for ws in list(self.ws_clients):
            try:
                await ws.send_str(data)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.ws_clients.discard(ws)

    async def handle_index(self, request):
        return web.FileResponse(STATIC_DIR / "index.html")

    def get_raw_jpeg(self) -> Optional[bytes]:
        return self.arenacam.latest_frame

    def get_overlay_jpeg(self) -> Optional[bytes]:
        return self.arena.latest_overlay_jpeg or self.get_raw_jpeg()

    def get_crop_jpeg(self) -> Optional[bytes]:
        if self.arena.latest_cropped_jpeg is not None:
            return self.arena.latest_cropped_jpeg

        raw = self.get_raw_jpeg()
        if raw is None:
            return None

        frame = _decode_jpeg(raw)
        if frame is None:
            return raw

        frame = _draw_waiting_overlay(frame)
        return _encode_jpeg(frame, quality=80)

    async def mjpeg_stream(self, request, frame_getter):
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "multipart/x-mixed-replace; boundary=frame",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

        await response.prepare(request)

        try:
            while not self.stop_event.is_set():
                jpeg = frame_getter()

                if jpeg is not None:
                    await response.write(
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: "
                        + str(len(jpeg)).encode("ascii")
                        + b"\r\n\r\n"
                        + jpeg
                        + b"\r\n"
                    )

                await asyncio.sleep(1 / 30)

        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception:
            pass

        return response

    async def handle_video_stream(self, request):
        self.logger.info("Web client connected to /video")
        response = await self.mjpeg_stream(request, self.get_raw_jpeg)
        self.logger.info("Web client disconnected from /video")
        return response

    async def handle_overlay_stream(self, request):
        self.logger.info("Web client connected to /overlay")
        response = await self.mjpeg_stream(request, self.get_overlay_jpeg)
        self.logger.info("Web client disconnected from /overlay")
        return response

    async def handle_crop_stream(self, request):
        self.logger.info("Web client connected to /crop")
        response = await self.mjpeg_stream(request, self.get_crop_jpeg)
        self.logger.info("Web client disconnected from /crop")
        return response

    async def handle_ws(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.ws_clients.add(ws)
        self.logger.info("WebSocket client connected to /ws")

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    pass
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            self.ws_clients.discard(ws)
            self.logger.info("WebSocket client disconnected from /ws")

        return ws

    async def handle_randomize(self, request):
        if hasattr(self.arena, "randomize_mission_overlay"):
            result = self.arena.randomize_mission_overlay()
            return web.json_response({"ok": True, **result})

        return web.json_response(
            {
                "ok": False,
                "error": "ArenaProcessor has no randomize_mission_overlay() method.",
            },
            status=500,
        )

    async def handle_restart(self, request):
        if not self.restart_password:
            return web.json_response(
                {
                    "ok": False,
                    "error": "Restart is not configured.",
                    "message": "Restart is not configured.",
                },
                status=503,
            )

        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {
                    "ok": False,
                    "error": "Invalid JSON body.",
                    "message": "Invalid JSON body.",
                },
                status=400,
            )

        password = str(data.get("password", ""))

        if password != self.restart_password:
            self.logger.warning("Rejected restart request due to invalid password")
            return web.json_response(
                {
                    "ok": False,
                    "error": "Invalid password.",
                    "message": "Invalid password.",
                },
                status=403,
            )

        self.logger.warning("Accepted authenticated restart request from web client")
        asyncio.create_task(_restart_process_after_delay())

        return web.json_response(
            {
                "ok": True,
                "message": "Restarting vision system...",
            }
        )


def create_app(stop_event, arenacam, arena_processor, restart_password: str = ""):
    page = WebPage(
        stop_event=stop_event,
        arenacam=arenacam,
        arena_processor=arena_processor,
        restart_password=restart_password,
    )
    return page.app