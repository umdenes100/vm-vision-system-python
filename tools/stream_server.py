# Make sure to do: pip install flask
from flask import Flask, Response
import subprocess

app = Flask(__name__)

PORT_IN = 5000
PORT_WEB = 8080

GST_CMD = [
    "gst-launch-1.0",
    "udpsrc", f"port={PORT_IN}",
    "caps=application/x-rtp,media=video,encoding-name=H264,clock-rate=90000,payload=96",
    "!", "rtpjitterbuffer", "latency=250",
    "!", "rtph264depay",
    "!", "h264parse",
    "!", "avdec_h264",
    "!", "videoconvert",
    "!", "jpegenc",
    "!", "multipartmux", "boundary=frame",
    "!", "fdsink"
]

def generate():
    proc = subprocess.Popen(
        GST_CMD,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0
    )

    try:
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            yield chunk
    finally:
        proc.kill()

@app.route("/")
def index():
    return """
    <html>
      <body style="margin:0;background:black;text-align:center;">
        <img src="/stream" style="max-width:100vw;max-height:100vh;">
      </body>
    </html>
    """

@app.route("/stream")
def stream():
    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT_WEB, threaded=True)
