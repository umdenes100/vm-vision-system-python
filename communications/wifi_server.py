import asyncio
import base64
import json
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Any, Callable, List
from collections import deque
from pathlib import Path

import cv2
import numpy as np
from aiohttp import web, WSMsgType

from utils.logging import web_info, web_warn, web_error, team_raw, emit_team_roster, emit_team_ml_image
from machinelearning.predictor import Predictor


@dataclass
class TeamState:
    name: str
    connected: bool = False
    team_type: str = ""
    aruco_id: int = -1

    x: float = -1.0
    y: float = -1.0
    theta: float = -1.0

    # (x, y, theta, is_visible) newest at right
    pose_hist: deque = field(default_factory=lambda: deque(maxlen=5))

    missed_pongs: int = 0
    last_seen_monotonic: float = field(default_factory=time.monotonic)


class WifiServer:
    """
    ESP <-> Vision system WebSocket server.

    Ops supported (incoming):
      - begin: {op:"begin", teamName, aruco:int, teamType:str}
      - print: {op:"print", teamName, message:str}
      - ping:  {op:"ping", teamName, status:"ping"|"pong"}
      - aruco: {op:"aruco", teamName}
      - prediction_request: {op:"prediction_request", teamName, index:int, frame:str(base64 jpeg)}

    Replies:
      - ping: {op:"ping", teamName, status:"pong"} when ESP pings
      - aruco: {op:"aruco", x,y,theta,is_visible}
      - prediction: {op:"prediction", prediction:int}
    """

    def __init__(
        self,
        host: str,
        port: int,
        get_marker_pose: Callable[[int], Tuple[float, float, float]],
        is_marker_seen: Callable[[int], bool],
        models_dir: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.get_marker_pose = get_marker_pose
        self.is_marker_seen = is_marker_seen

        self._app = web.Application()
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

        self._stop = asyncio.Event()

        self.teams: Dict[str, TeamState] = {}
        self._sockets: Dict[str, web.WebSocketResponse] = {}

        self._ping_task: Optional[asyncio.Task] = None
        self._roster_task: Optional[asyncio.Task] = None

        # ML Predictor
        self._predictor = Predictor(models_dir=models_dir)

        self._app.router.add_get("/", self._health)
        self._app.router.add_get("/ws", self._ws_handler)

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app, access_log=None)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

        self._ping_task = asyncio.create_task(self._ping_loop())
        self._roster_task = asyncio.create_task(self._roster_loop())

        web_info(f"ESP WiFi Server running on ws://{self.host}:{self.port}/ws")

    async def stop(self) -> None:
        self._stop.set()

        for name, ws in list(self._sockets.items()):
            try:
                await ws.close()
            except Exception:
                pass
            self._sockets.pop(name, None)

        for t in [self._ping_task, self._roster_task]:
            if t:
                t.cancel()
                try:
                    await t
                except Exception:
                    pass

        if self._site:
            try:
                await self._site.stop()
            except Exception:
                pass

        if self._runner:
            try:
                await self._runner.cleanup()
            except Exception:
                pass

    async def _health(self, _request: web.Request) -> web.Response:
        return web.Response(text="OK")

    def _update_team_pose_and_history(self, st: TeamState) -> None:
        x, y, th = (-1.0, -1.0, -1.0)

        if st.connected and st.aruco_id >= 0:
            if self.is_marker_seen(st.aruco_id):
                x, y, th = self.get_marker_pose(st.aruco_id)
            else:
                x, y, th = (-1.0, -1.0, -1.0)

        st.x, st.y, st.theta = float(x), float(y), float(th)
        visible = (st.x != -1.0 and st.y != -1.0 and st.theta != -1.0)
        st.pose_hist.append((st.x, st.y, st.theta, bool(visible)))

    def _snapshot_roster(self) -> List[Dict[str, Any]]:
        out = []
        for name, st in sorted(self.teams.items(), key=lambda kv: kv[0].lower()):
            self._update_team_pose_and_history(st)
            visible = (st.x != -1.0 and st.y != -1.0 and st.theta != -1.0)

            out.append(
                {
                    "name": st.name,
                    "connected": bool(st.connected),
                    "teamType": st.team_type,
                    "aruco": int(st.aruco_id),
                    "visible": bool(visible),
                    "x": float(st.x),
                    "y": float(st.y),
                    "theta": float(st.theta),
                }
            )
        return out

    def _push_roster_to_ui(self) -> None:
        emit_team_roster(self._snapshot_roster())

    async def _roster_loop(self) -> None:
        try:
            while not self._stop.is_set():
                self._push_roster_to_ui()
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            return

    async def _ping_loop(self) -> None:
        try:
            while not self._stop.is_set():
                await asyncio.sleep(5.0)

                for name, ws in list(self._sockets.items()):
                    st = self.teams.get(name)
                    if st is None or not st.connected:
                        continue

                    try:
                        await ws.send_str(json.dumps({"op": "ping", "teamName": name, "status": "ping"}))
                    except Exception:
                        await self._mark_disconnected(name)
                        continue

                    st.missed_pongs += 1
                    if st.missed_pongs >= 5:
                        web_warn(f"{name} lost connection (ping timeout)")
                        await self._mark_disconnected(name)
        except asyncio.CancelledError:
            return

    async def _mark_disconnected(self, team_name: str) -> None:
        st = self.teams.get(team_name)
        if st:
            st.connected = False
        ws = self._sockets.pop(team_name, None)
        if ws:
            try:
                await ws.close()
            except Exception:
                pass
        web_info(f"{team_name} lost connection")
        self._push_roster_to_ui()

    def _best_recent_pose(self, st: TeamState) -> Tuple[float, float, float, bool]:
        self._update_team_pose_and_history(st)
        for (x, y, th, vis) in reversed(st.pose_hist):
            if vis and x != -1.0 and y != -1.0 and th != -1.0:
                return float(x), float(y), float(th), True
        return -1.0, -1.0, -1.0, False

    @staticmethod
    def _decode_base64_jpeg_to_bgr(frame_b64: str) -> Optional[np.ndarray]:
        try:
            raw = base64.b64decode(frame_b64.encode())
            arr = np.frombuffer(raw, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            return img
        except Exception:
            return None

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        team_name: Optional[str] = None

        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue

                try:
                    data = json.loads(msg.data)
                except Exception:
                    continue

                op = str(data.get("op", "")).strip().lower()
                tname = str(data.get("teamName", "")).strip()
                if not tname:
                    continue

                if team_name is None:
                    team_name = tname

                st = self.teams.get(tname)
                if st is None:
                    st = TeamState(name=tname)
                    self.teams[tname] = st

                st.last_seen_monotonic = time.monotonic()

                if op == "begin":
                    st.connected = True
                    st.team_type = str(data.get("teamType", "")).strip()
                    try:
                        st.aruco_id = int(data.get("aruco", -1))
                    except Exception:
                        st.aruco_id = -1
                    st.missed_pongs = 0

                    self._sockets[tname] = ws
                    web_info(f"{tname} has connected")
                    self._push_roster_to_ui()

                elif op == "print":
                    # ESP prints: show exactly as sent (no [INFO])
                    message = str(data.get("message", ""))
                    team_raw(tname, message)

                elif op == "ping":
                    status = str(data.get("status", "")).strip().lower()
                    if status == "ping":
                        st.missed_pongs = 0
                        try:
                            await ws.send_str(json.dumps({"op": "ping", "teamName": tname, "status": "pong"}))
                        except Exception:
                            await self._mark_disconnected(tname)
                    elif status == "pong":
                        st.missed_pongs = 0

                elif op == "aruco":
                    x, y, th, vis = self._best_recent_pose(st)
                    try:
                        await ws.send_str(
                            json.dumps(
                                {"op": "aruco", "x": float(x), "y": float(y), "theta": float(th), "is_visible": bool(vis)}
                            )
                        )
                    except Exception:
                        await self._mark_disconnected(tname)

                elif op == "prediction_request":
                    # Required fields: index:int, frame:str(base64 jpeg)
                    try:
                        model_index = int(data.get("index"))
                    except Exception:
                        model_index = -1

                    frame_b64 = data.get("frame")
                    if not isinstance(frame_b64, str) or len(frame_b64) < 8:
                        web_error(f"ML request from {tname} missing/invalid frame")
                        continue

                    img = self._decode_base64_jpeg_to_bgr(frame_b64)
                    if img is None:
                        web_error(f"ML request from {tname} had undecodable frame")
                        continue

                    # Push the request image to the UI for that team
                    # UI expects a data URL
                    emit_team_ml_image(tname, "data:image/jpeg;base64," + frame_b64)

                    # Run prediction in a thread to avoid blocking the asyncio loop
                    try:
                        pred = await asyncio.to_thread(self._predictor.predict, img, tname, model_index)
                    except Exception as e:
                        web_error(f"ML prediction failed for {tname} idx={model_index}: {e}")
                        continue

                    # Reply to ESP
                    try:
                        await ws.send_str(json.dumps({"op": "prediction", "prediction": int(pred)}))
                    except Exception:
                        await self._mark_disconnected(tname)

                else:
                    pass

        except asyncio.CancelledError:
            pass
        finally:
            if team_name:
                await self._mark_disconnected(team_name)

        return ws
