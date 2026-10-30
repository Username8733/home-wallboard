"""Local-only camera analysis. No frames are written to disk or sent over the network."""

import ctypes
import json
import logging
import pathlib
import time

# Camera buffers must never enter crash dumps.
ctypes.CDLL(None).prctl(4, 0, 0, 0, 0)
import cv2  # noqa: E402
import gi  # noqa: E402
import numpy as np  # noqa: E402

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

logging.basicConfig(level=logging.INFO)
cv2.setNumThreads(1)
Gst.init(None)
state = pathlib.Path("/run/wallboard/presence.json")
face = cv2.CascadeClassifier("/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml")
profile = cv2.CascadeClassifier("/usr/share/opencv4/haarcascades/haarcascade_profileface.xml")
p = Gst.Pipeline.new("presence")
src = Gst.ElementFactory.make("libcamerasrc")
src.set_property("camera-name", "\\_SB_.PCI0.LNK1")
caps = Gst.ElementFactory.make("capsfilter")
caps.set_property("caps", Gst.Caps.from_string("video/x-raw,width=640,height=480,format=NV12"))
sink = Gst.ElementFactory.make("appsink")
sink.set_property("sync", False)
sink.set_property("max-buffers", 1)
sink.set_property("drop", True)
for el in (src, caps, sink):
    p.add(el)
assert src.link(caps) and caps.link(sink)
p.set_state(Gst.State.PLAYING)
last_seen = 0
frames = 0
last_log = 0
while True:
    sample = sink.emit("try-pull-sample", 10 * Gst.SECOND)
    if sample is None:
        raise RuntimeError("Camera stopped delivering frames")
    buf = sample.get_buffer()
    ok, m = buf.map(Gst.MapFlags.READ)
    if not ok:
        raise RuntimeError("Could not map camera frame")
    try:
        # NV12 starts with a full-resolution luminance plane; no colour conversion needed.
        gray = np.frombuffer(m.data, dtype=np.uint8, count=640 * 480).reshape(480, 640).copy()
    finally:
        buf.unmap(m)
    gray = cv2.equalizeHist(gray)
    faces = face.detectMultiScale(gray, 1.15, 5, minSize=(64, 64))
    if len(faces) == 0:
        faces = profile.detectMultiScale(gray, 1.15, 5, minSize=(64, 64))
    if len(faces) == 0:
        faces = profile.detectMultiScale(cv2.flip(gray, 1), 1.15, 5, minSize=(64, 64))
    now = time.time()
    frames += 1
    if len(faces):
        last_seen = now
    data = {
        "camera_ok": True,
        "last_frame": now,
        "last_seen": last_seen,
        "faces": len(faces),
        "frames": frames,
        "minimum_face_pixels": 64,
    }
    tmp = state.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(state)
    if now - last_log > 60:
        logging.info("Camera healthy, frames=%s, faces=%s", frames, len(faces))
        last_log = now
    time.sleep(0.5)
