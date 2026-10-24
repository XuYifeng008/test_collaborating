"""Synthetic perception stubs for injected-perception protocol tests.

The real platform would send RGB frames; the public recorded fixtures have the
image payloads removed, and this offline harness cannot simulate a camera.  For
the C07 place -> tare -> pour -> read state-machine test only, the harness
monkeypatches the policy's module-level ``perceive`` hook with the fake below.

**This is a synthetic perception stub.  It proves the state machine and protocol
handling only; it does not claim real perception, real physics or task success.**

Blob layout follows the policy's documented hook contract:
``{"cx","cy","image_w","image_h"}`` plus optional size fields.  Everything is
centred on the servo goal pixel ``(0.5*W, 0.55*H)`` so image-space servoing
converges immediately.
"""
from __future__ import annotations

import math

DEFAULT_IMAGE_W = 640.0
DEFAULT_IMAGE_H = 480.0
GOAL_FRACTION = (0.5, 0.55)

#: Perceive kinds the policy may ask for; anything else also gets a centred blob.
BLOB_KINDS = (
    "bright",
    "dark",
    "white",
    "green",
    "blue",
    "cup_receiving",
    "pan",
    "cup_source",
    "caps",
    "frames",
)


class SyntheticPerception:
    """Callable matching the policy's ``perceive(observation, kind, camera)`` hook."""

    synthetic = True

    def __init__(self, image_w=DEFAULT_IMAGE_W, image_h=DEFAULT_IMAGE_H):
        self.image_w = float(image_w)
        self.image_h = float(image_h)
        self.cx = GOAL_FRACTION[0] * self.image_w
        self.cy = GOAL_FRACTION[1] * self.image_h
        self.calls = {}
        self.missing = None  # set to a kind to simulate "perception unavailable" for it

    def _blob(self, dx=0.0, dy=0.0, size=80.0):
        return {
            "cx": self.cx + float(dx),
            "cy": self.cy + float(dy),
            "image_w": self.image_w,
            "image_h": self.image_h,
            "width_px": float(size),
            "height_px": float(size),
            "x0": self.cx - size / 2.0,
            "x1": self.cx + size / 2.0,
            "y0": self.cy - size / 2.0,
            "y1": self.cy + size / 2.0,
            "area_px": float(size * size),
            "camera": "synthetic-overhead",
            "synthetic": True,
        }

    def __call__(self, observation, kind, camera=None):
        self.calls[kind] = self.calls.get(kind, 0) + 1
        if self.missing is not None and kind == self.missing:
            return None
        try:
            kind = str(kind)
        except Exception:  # pragma: no cover - defensive
            return None
        if kind == "liquid":
            # Monotone synthetic fill ramp; not used by the C07 state machine.
            fraction = min(0.55, 0.02 * self.calls[kind])
            return {"fill_fraction": fraction, "level_row": int(self.image_h * (1.0 - fraction)),
                    "synthetic": True}
        if kind == "caps":
            return [self._blob(), self._blob(dx=60.0, size=48.0)]
        if kind == "frames":
            return {"green": self._blob(dx=-40.0), "blue": self._blob(dx=40.0)}
        if kind in BLOB_KINDS:
            return self._blob()
        return self._blob()

    def summary(self):
        return {
            "synthetic": True,
            "notice": "synthetic perception stub; state-machine/protocol validation only",
            "image_wh": [self.image_w, self.image_h],
            "goal_px": [self.cx, self.cy],
            "calls": dict(sorted(self.calls.items())),
            "missing_kind": self.missing,
        }


def build_perception_patch(*, image_w=DEFAULT_IMAGE_W, image_h=DEFAULT_IMAGE_H, missing=None):
    """Return ``(stub, module_patch)`` for ``run_episode(policy_module_patch=...)``."""
    stub = SyntheticPerception(image_w=image_w, image_h=image_h)
    stub.missing = missing

    def patch(module):
        module.perceive = stub
        setattr(module, "_synthetic_perceive_installed", True)

    return stub, patch
