import asyncio
from aiohttp import web, WSMsgType
import cv2
import numpy as np


class WebPage:
    def __init__(self, arena_processor, wifi_server):
        self.arena = arena_processor
        self.wifi = wifi_server
        self.app = web.Application()
        self.ws_clients = set()

        self.setup_routes()

    def setup_routes(self):
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/video", self.handle_video)
        self.app.router.add_get("/overlay", self.handle_overlay)
        self.app.router.add_get("/crop", self.handle_crop)
        self.app.router.add_get("/ws", self.handle_ws)

        self.app.router.add_post("/api/randomize", self.handle_randomize)
        self.app.router.add_post("/api/restart", self.handle_restart)

    async def handle_index(self, request):
        return web.FileResponse("frontend/static/index.html")

    async def handle_video(self, request):
        return web.Response(
            body=self.arena.latest_raw_jpeg or b"",
            content_type="image/jpeg"
        )

    async def handle_overlay(self, request):
        return web.Response(
            body=self.arena.latest_overlay_jpeg or b"",
            content_type="image/jpeg"
        )

    async def handle_crop(self, request):
        """
        If crop exists → return it
        If not → show RAW frame with overlay text instead of black screen
        """
        if self.arena.latest_cropped_jpeg is not None:
            return web.Response(
                body=self.arena.latest_cropped_jpeg,
                content_type="image/jpeg"
            )

        # --- RAW FALLBACK WITH TEXT ---
        if self.arena.latest_raw_jpeg is not None:
            frame = cv2.imdecode(
                np.frombuffer(self.arena.latest_raw_jpeg, dtype=np.uint8),
                cv2.IMREAD_COLOR
            )

            if frame is not None:
                h, w = frame.shape[:2]

                text = "Waiting for crop transform..."

                font = cv2.FONT_HERSHEY_SIMPLEX
                scale = 1
                thickness = 2

                (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
                x = (w - tw) // 2
                y = (h + th) // 2

                # black outline
                cv2.putText(frame, text, (x, y),
                            font, scale, (0, 0, 0), thickness + 3, cv2.LINE_AA)

                # white text
                cv2.putText(frame, text, (x, y),
                            font, scale, (255, 255, 255), thickness, cv2.LINE_AA)

                _, jpeg = cv2.imencode(".jpg", frame)

                return web.Response(
                    body=jpeg.tobytes(),
                    content_type="image/jpeg"
                )

        # fallback if nothing available
        return web.Response(body=b"", content_type="image/jpeg")

    async def handle_ws(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.ws_clients.add(ws)

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                pass
            elif msg.type == WSMsgType.ERROR:
                print("WebSocket error:", ws.exception())

        self.ws_clients.remove(ws)
        return ws

    async def handle_randomize(self, request):
        if hasattr(self.arena, "randomize_mission"):
            self.arena.randomize_mission()
        return web.json_response({"status": "ok"})

    async def handle_restart(self, request):
        import os
        os._exit(0)

    def run(self, host="0.0.0.0", port=8080):
        web.run_app(self.app, host=host, port=port)


# ✅ REQUIRED FOR YOUR MAIN.PY
def create_app(arena_processor, wifi_server):
    page = WebPage(arena_processor, wifi_server)
    return page.app