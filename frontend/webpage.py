import asyncio
from aiohttp import web
from utils.logging import get_logger

HTML = """
<!doctype html>
<html>
  <head>
    <title>VM Vision System</title>
  </head>
  <body>
    <h1>Raw Video Feed</h1>
    <img src="/video" />
  </body>
</html>
"""


def create_app(arenacam):
    logger = get_logger("frontend")
    app = web.Application()

    async def index(request):
        return web.Response(text=HTML, content_type="text/html")

    async def video(request):
        response = web.StreamResponse(
            headers={
                "Content-Type": "multipart/x-mixed-replace; boundary=frame"
            }
        )
        await response.prepare(request)
        logger.info("Web client connected")

        try:
            while True:
                frame = arenacam.latest_frame
                if frame:
                    await response.write(
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" +
                        frame + b"\r\n"
                    )
                await asyncio.sleep(0.05)
        except Exception:
            pass
        finally:
            logger.info("Web client disconnected")

        return response

    app.router.add_get("/", index)
    app.router.add_get("/video", video)
    return app
