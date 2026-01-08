import os
import time
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests


# === Firebase config (mirrors the old vision system listener) ===
FIREBASE_API_KEY = "AIzaSyBAMDAGYHNMtPaXAwJl-BRvxvl37E7Z3xE"
FIREBASE_PROJECT_ID = "engr-enes100tool-inv-firebase"
FIREBASE_DB_URL = "https://engr-enes100tool-inv-firebase-model-watcher.firebaseio.com/"
FIREBASE_STORAGE_BUCKET = "engr-enes100tool-inv-firebase.appspot.com"

# Storage folder
REMOTE_PREFIX = "studentmodels/"  # Firebase Storage “folder”


def _repo_root() -> str:
    # machinelearning/ is at repo root
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


DEFAULT_OUTPUT_DIR = os.path.join(_repo_root(), "machinelearning", "models")


def log(msg: str) -> None:
    # Keep formatting close to the legacy script
    print(msg, flush=True)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def parse_rfc3339(ts: str) -> float:
    """Firebase Storage returns RFC3339 timestamps like '2024-01-01T12:34:56.789Z'."""
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def list_storage_items(prefix: str) -> List[Dict[str, Any]]:
    """List objects in Firebase Storage under a prefix."""
    url = f"https://firebasestorage.googleapis.com/v0/b/{FIREBASE_STORAGE_BUCKET}/o"
    params = {"prefix": prefix, "key": FIREBASE_API_KEY}

    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("items", []) or []


def build_download_url(object_name: str, download_tokens: str) -> str:
    """Build a direct download URL from Firebase Storage object metadata."""
    token = ""
    if download_tokens:
        token = str(download_tokens).split(",")[0].strip()

    enc_name = quote(object_name, safe="")
    url = f"https://firebasestorage.googleapis.com/v0/b/{FIREBASE_STORAGE_BUCKET}/o/{enc_name}?alt=media"
    if token:
        url += f"&token={quote(token, safe='')}"
    return url


def download_file(object_name: str, filename_only: str, output_dir: str, download_tokens: str) -> None:
    """Download to output_dir/filename_only atomically (.tmp then replace)."""
    ensure_dir(output_dir)

    dst = os.path.join(output_dir, filename_only)
    tmp = dst + ".tmp"

    url = build_download_url(object_name, download_tokens)
    r = requests.get(url, stream=True, timeout=30)
    r.raise_for_status()

    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except OSError:
        pass

    with open(tmp, "wb") as f:
        for chunk in r.iter_content(chunk_size=64 * 1024):
            if chunk:
                f.write(chunk)

    os.replace(tmp, dst)


def check_once(output_dir: str) -> None:
    ensure_dir(output_dir)
    log("[listener] Executing check")

    items = list_storage_items(REMOTE_PREFIX)

    for item in items:
        obj_name = str(item.get("name", ""))
        if not obj_name.startswith(REMOTE_PREFIX):
            continue

        filename = obj_name[len(REMOTE_PREFIX):]
        if not filename:
            continue

        updated = str(item.get("updated", ""))
        remote_ts = parse_rfc3339(updated) if updated else 0.0
        tokens = str(item.get("downloadTokens", "") or "")

        local_path = os.path.join(output_dir, filename)

        if os.path.exists(local_path):
            local_ts = os.path.getmtime(local_path)
            if local_ts < remote_ts:
                log(f"[listener] Downloading {filename} (local {local_ts:.3f} < remote {remote_ts:.3f})")
                download_file(obj_name, filename, output_dir, tokens)
                try:
                    os.utime(local_path, (time.time(), remote_ts))
                except Exception:
                    pass
                log(f"[listener] Downloaded {filename}")
            else:
                log(f"[listener] Skipping {filename} (local {local_ts:.3f} >= remote {remote_ts:.3f})")
        else:
            log(f"[listener] Downloading {filename} (missing locally)")
            download_file(obj_name, filename, output_dir, tokens)
            try:
                os.utime(local_path, (time.time(), remote_ts))
            except Exception:
                pass
            log(f"[listener] Downloaded {filename}")


@dataclass
class Debouncer:
    delay_s: float = 0.25
    _lock: threading.Lock = threading.Lock()
    _scheduled: bool = False
    _timer: Optional[threading.Timer] = None

    def schedule(self, fn) -> None:
        with self._lock:
            if self._scheduled:
                return
            self._scheduled = True

            def run():
                try:
                    fn()
                except Exception as e:
                    log(f"[listener] check() failed: {e}")
                    os._exit(1)
                finally:
                    with self._lock:
                        self._scheduled = False
                        self._timer = None

            self._timer = threading.Timer(self.delay_s, run)
            self._timer.daemon = True
            self._timer.start()


def db_event_stream_loop(debouncer: Debouncer, output_dir: str, stop_evt: threading.Event) -> None:
    """Listen for RTDB changes via Firebase REST streaming (SSE)."""
    url = FIREBASE_DB_URL.rstrip("/") + "/.json"
    params = {"print": "silent"}
    headers = {"Accept": "text/event-stream"}

    while not stop_evt.is_set():
        try:
            log("[listener] Connecting to Firebase RTDB event stream")
            with requests.get(url, params=params, headers=headers, stream=True, timeout=60) as r:
                r.raise_for_status()

                for raw_line in r.iter_lines(decode_unicode=True):
                    if stop_evt.is_set():
                        return
                    if not raw_line:
                        continue

                    line = raw_line.strip()
                    if line.startswith("event:"):
                        evt = line.split(":", 1)[1].strip().lower()
                        if evt in ("put", "patch"):
                            log("[listener] Database changed -> scheduling check")
                            debouncer.schedule(lambda: check_once(output_dir))
                    elif line.startswith("data:"):
                        payload = line.split(":", 1)[1].strip()
                        if payload and payload != "null":
                            debouncer.schedule(lambda: check_once(output_dir))

        except requests.exceptions.ReadTimeout:
            continue
        except Exception as e:
            log(f"[listener] RTDB stream error: {e} (reconnecting in 2s)")
            time.sleep(2)


def main() -> None:
    output_dir = os.environ.get("VISION_ML_MODELS_DIR", DEFAULT_OUTPUT_DIR)

    # Initial sync
    check_once(output_dir)

    debouncer = Debouncer(delay_s=0.25)
    stop_evt = threading.Event()

    t = threading.Thread(
        target=db_event_stream_loop,
        args=(debouncer, output_dir, stop_evt),
        daemon=True,
    )
    t.start()

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        log("[listener] Shutdown requested (Ctrl+C)")
        stop_evt.set()
        time.sleep(0.2)


if __name__ == "__main__":
    main()
