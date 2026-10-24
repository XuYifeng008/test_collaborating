"""Perception smoke on the one real public PNG shipped with the public kit.

The public kit only ships a single recorded PNG payload (removed platform IDs);
this checks that the policy-side RGB helpers decode it and run without relying
on private data or network access.
"""

import json
import os
import sys

ROOT = r"E:\dev\agents\lark-working"
PUB = os.path.join(ROOT, "inbox", "1024-test", "自主实验赛道选手公开包")
SRC = os.path.join(ROOT, "deliverables", "2026-10-24-nine-task", "src", "my-policy")
sys.path.insert(0, PUB)
sys.path.insert(0, SRC)

import vision  # noqa: E402

payload = json.load(open(os.path.join(PUB, "examples", "sdk-public-image.json"),
                         encoding="utf-8"))
print("schema:", payload.get("schema"))
image = payload.get("image") or payload
if not isinstance(image, dict) or "base64" not in image:
    # tolerate a wrapped structure
    for key in ("payload", "data", "png"):
        if isinstance(payload.get(key), dict) and "base64" in payload[key]:
            image = payload[key]
            break
observation = {"images": {"public": image}}
rgb = vision.decode(observation, "public")
print("decoded:", None if rgb is None else rgb.shape, None if rgb is None else rgb.dtype,
      "mean:", None if rgb is None else [round(float(x), 2) for x in rgb.reshape(-1, 3).mean(axis=0)])
print("camera_ids:", vision.camera_ids(observation), "picked:",
      vision.pick_camera(observation, ["overhead", "global", "public"]))
print("detect_frames:", (vision.detect_frames(observation, "public") or {}).keys())
caps = vision.detect_white_caps(observation, "public")
print("white_cap_blobs:", None if caps is None else len(caps))
print("bright:", (vision.detect_bright_or_dark(observation, "bright", "public") or {}).get("area_px"))
print("dark:", (vision.detect_bright_or_dark(observation, "dark", "public") or {}).get("area_px"))
level = vision.estimate_liquid_line(observation, "public")
print("liquid_line:", level)
assert rgb is not None and rgb.ndim == 3 and rgb.shape[2] == 3
print("PERCEPTION SMOKE: PASS")
