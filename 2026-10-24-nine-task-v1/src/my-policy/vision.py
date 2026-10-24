"""Public-RGB perception helpers for the nine-task policy.

Everything here consumes only the camera payloads that the platform already
sent to the policy through ``observation['images']``.  No file paths, URLs,
private object poses or judge state are touched.  The functions are pure
NumPy/Pillow so they behave the same with or without OpenCV installed
(the execution profile ships NumPy 1.26.4 / Pillow 11.3.0 /
opencv-python-headless 4.11.0.86; OpenCV is optional here on purpose).

Detections are *best-effort hints* for the controller.  A ``None`` return
means "not confidently detected" and callers must degrade safely instead of
guessing.
"""

import math

import numpy as np


# --------------------------------------------------------------------------
# decoding (only supplied public PNG payloads; mirrors lab_sdk.images limits)
# --------------------------------------------------------------------------
def decode(observation, camera_id):
    """Return HxWx3 uint8 RGB for a public camera payload, or None."""
    try:
        images = observation.get("images") or {}
        image = images.get(camera_id)
        if not isinstance(image, dict):
            return None
        try:
            from lab_sdk.images import numpy_rgb  # public SDK helper
            return np.asarray(numpy_rgb(image))
        except Exception:
            import base64
            import io
            from PIL import Image
            encoded = image.get("base64")
            if not isinstance(encoded, str):
                return None
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) > 16 * 1024 * 1024 or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                return None
            value = Image.open(io.BytesIO(raw))
            if value.width * value.height > 16 * 1024 * 1024:
                return None
            value.load()
            return np.asarray(value.convert("RGB")).copy()
    except Exception:
        return None


def camera_ids(observation):
    images = observation.get("images") or {}
    return [str(k) for k in images.keys()]


def pick_camera(observation, preferred):
    ids = camera_ids(observation)
    for want in preferred:
        for cid in ids:
            if want == cid or want in cid:
                return cid
    return None


# --------------------------------------------------------------------------
# colour masks and blobs (pure NumPy, downsampled for CPU safety)
# --------------------------------------------------------------------------
def _downsample(rgb, max_side=192):
    h, w = rgb.shape[:2]
    step = max(1, int(math.ceil(max(h, w) / float(max_side))))
    return rgb[::step, ::step], step


def _blob_label(mask, min_pixels=12):
    """Very small connected-component labeller (4-neighbour) for downsampled masks."""
    h, w = mask.shape
    seen = np.zeros((h, w), dtype=bool)
    blobs = []
    for y in range(h):
        row = mask[y]
        for x in range(w):
            if not row[x] or seen[y, x]:
                continue
            stack = [(y, x)]
            seen[y, x] = True
            xs = []
            ys = []
            while stack:
                cy, cx = stack.pop()
                xs.append(cx)
                ys.append(cy)
                if cy > 0 and mask[cy - 1, cx] and not seen[cy - 1, cx]:
                    seen[cy - 1, cx] = True
                    stack.append((cy - 1, cx))
                if cy + 1 < h and mask[cy + 1, cx] and not seen[cy + 1, cx]:
                    seen[cy + 1, cx] = True
                    stack.append((cy + 1, cx))
                if cx > 0 and mask[cy, cx - 1] and not seen[cy, cx - 1]:
                    seen[cy, cx - 1] = True
                    stack.append((cy, cx - 1))
                if cx + 1 < w and mask[cy, cx + 1] and not seen[cy, cx + 1]:
                    seen[cy, cx + 1] = True
                    stack.append((cy, cx + 1))
            n = len(xs)
            if n >= min_pixels:
                blobs.append({
                    "area": n,
                    "cx": float(sum(xs)) / n,
                    "cy": float(sum(ys)) / n,
                    "x0": int(min(xs)), "x1": int(max(xs)),
                    "y0": int(min(ys)), "y1": int(max(ys)),
                })
    blobs.sort(key=lambda b: -b["area"])
    return blobs


def _region_masks(rgb):
    """Greens (source frame) and blues (target frame / blue basket) masks."""
    rgb = rgb.astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    green = (g > 70) & (g > r + 25) & (g > b + 15)
    blue = (b > 70) & (b > r + 25) & (b > g + 10)
    bright = (r + g + b) / 3.0
    white = (bright > 150) & (abs(r - g) < 30) & (abs(g - b) < 30) & (abs(r - b) < 30)
    return {"green": green, "blue": blue, "white": white}


def detect_frames(observation, camera="overhead"):
    """Centroids of the green source area and blue target area in a camera."""
    cid = pick_camera(observation, [camera, "overhead", "global", "basket"])
    rgb = decode(observation, cid) if cid else None
    if rgb is None:
        return None
    small, step = _downsample(rgb)
    masks = _region_masks(small)
    out = {}
    for name in ("green", "blue"):
        blobs = _blob_label(masks[name], min_pixels=max(20, small.shape[0] // 20))
        if blobs:
            top = blobs[0]
            out[name] = {
                "camera": cid, "step": step,
                "cx": top["cx"] * step, "cy": top["cy"] * step,
                "x0": top["x0"] * step, "x1": top["x1"] * step,
                "y0": top["y0"] * step, "y1": top["y1"] * step,
                "width_px": (top["x1"] - top["x0"] + 1) * step,
                "height_px": (top["y1"] - top["y0"] + 1) * step,
                "area_px": top["area"] * step * step,
                "image_w": rgb.shape[1], "image_h": rgb.shape[0],
            }
    return out or None


def detect_white_caps(observation, camera="overhead"):
    """Bright cap blobs (bottle caps are white in the public layout)."""
    cid = pick_camera(observation, [camera, "overhead", "global", "basket"])
    rgb = decode(observation, cid) if cid else None
    if rgb is None:
        return None
    small, step = _downsample(rgb)
    masks = _region_masks(small)
    blobs = _blob_label(masks["white"], min_pixels=max(8, small.shape[0] // 60))
    if not blobs:
        return None
    return [{"camera": cid, "cx": b["cx"] * step, "cy": b["cy"] * step,
             "area_px": b["area"] * step * step,
             "image_w": rgb.shape[1], "image_h": rgb.shape[0]} for b in blobs[:8]]


def _blobs_for_kind(rgb, kind, min_pixels):
    rgb = rgb.astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    bright = (r + g + b) / 3.0
    if kind == "white":
        mask = (bright > 150) & (abs(r - g) < 30) & (abs(g - b) < 30) & (abs(r - b) < 30)
    elif kind == "bright":
        mask = bright > 140
    elif kind == "dark":
        mask = bright < 70
    else:
        raise ValueError("unsupported kind")
    return _blob_label(mask, min_pixels=min_pixels)


def detect_bright_or_dark(observation, kind="bright", camera=None, min_pixels=24):
    """Single largest bright/dark blob (used for cups, pan, knob, rack holes)."""
    cid = pick_camera(observation, [camera, "overhead", "global", "basket", "tube"]) if camera else \
        pick_camera(observation, ["overhead", "global", "basket", "tube"])
    rgb = decode(observation, cid) if cid else None
    if rgb is None:
        return None
    small, step = _downsample(rgb)
    blobs = _blobs_for_kind(small, kind, max(int(min_pixels), small.shape[0] // 40))
    if not blobs:
        return None
    b = blobs[0]
    return {"camera": cid, "cx": b["cx"] * step, "cy": b["cy"] * step,
            "x0": b["x0"] * step, "x1": b["x1"] * step,
            "y0": b["y0"] * step, "y1": b["y1"] * step,
            "width_px": (b["x1"] - b["x0"] + 1) * step,
            "height_px": (b["y1"] - b["y0"] + 1) * step,
            "area_px": b["area"] * step * step,
            "image_w": rgb.shape[1], "image_h": rgb.shape[0]}


def detect_bright_blobs(observation, camera=None, limit=4):
    cid = pick_camera(observation, [camera, "overhead", "global", "basket", "tube"]) if camera else \
        pick_camera(observation, ["overhead", "global", "basket", "tube"])
    rgb = decode(observation, cid) if cid else None
    if rgb is None:
        return None
    small, step = _downsample(rgb)
    blobs = _blobs_for_kind(small, "bright", max(16, small.shape[0] // 60))
    if not blobs:
        return None
    return [{"camera": cid, "cx": b["cx"] * step, "cy": b["cy"] * step,
             "area_px": b["area"] * step * step,
             "width_px": (b["x1"] - b["x0"] + 1) * step,
             "height_px": (b["y1"] - b["y0"] + 1) * step,
             "image_w": rgb.shape[1], "image_h": rgb.shape[0]} for b in blobs[:limit]]


def estimate_liquid_line(observation, camera="overhead", roi=None):
    """Best-effort horizontal liquid surface line inside a cylinder ROI.

    Returns a normalised fill fraction (0..1) if a stable, high-contrast
    horizontal edge is found, else None.  C02 is only allowed to use such RGB
    information; this helper never reads a private volume field.
    """
    cid = pick_camera(observation, [camera, "overhead", "global", "basket", "tube"])
    rgb = decode(observation, cid) if cid else None
    if rgb is None:
        return None
    h, w = rgb.shape[:2]
    if roi is None:
        x0, x1, y0, y1 = int(0.35 * w), int(0.65 * w), int(0.15 * h), int(0.95 * h)
    else:
        x0, x1, y0, y1 = [int(v) for v in roi]
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    patch = rgb[y0:y1, x0:x1].astype(np.float32)
    gray = patch.mean(axis=2)
    # vertical gradient averaged over the ROI columns
    grad = np.abs(np.diff(gray, axis=0)).mean(axis=1)
    if grad.size < 4:
        return None
    # ignore the top/bottom 12% (rim, base) and require a clear peak
    lo = max(1, int(0.12 * grad.size))
    hi = max(lo + 1, int(0.88 * grad.size))
    band = grad[lo:hi]
    if band.size < 2:
        return None
    k = int(np.argmax(band)) + lo
    peak = float(band.max())
    med = float(np.median(band))
    if peak < med * 2.0 or peak < 3.0:
        return None
    fill = 1.0 - (float(k) / float(grad.size))
    return {"camera": cid, "level_row": int(k + y0), "fill_fraction": max(0.0, min(1.0, fill)),
            "contrast": peak, "image_h": h}


def center_offset(detection, image_shape):
    """(dx, dy) of a detection centroid from image centre, in pixels."""
    if not detection:
        return None
    h, w = image_shape[:2]
    return float(detection["cx"]) - w / 2.0, float(detection["cy"]) - h / 2.0
