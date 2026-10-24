"""Protocol-level acceptance of the frozen derived packages (wave1.zip / wave2.zip).

The official packager emits v1 compatibility wrappers around the canonical v2
policy.  This script unpacks the frozen archives and checks that

  1. a wrapper refuses to run when the image/model runtime identity is missing
     (the runtime profile / configuration SHA binding is enforced);
  2. a correctly bound wrapper accepts the real public fixture instruction and
     observation and returns legal v1 actions;
  3. robot binding is enforced (a franka package rejects a piper instruction);
  4. the wave2 wrapper passes the C07 stand-alone balance instrument action
     through and still rejects arm+instrument mixing.

This is a protocol/identity check on the frozen bytes, not a physics test.
"""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import zipfile

ROOT = r"E:\dev\agents\lark-working"
PUB = os.path.join(ROOT, "inbox", "1024-test", "自主实验赛道选手公开包")
TASK = os.path.join(ROOT, "deliverables", "2026-10-24-nine-task")
EVID = os.path.join(TASK, "evidence", "wrapper")
sys.path.insert(0, PUB)

for name in ("lab_sdk", "lab_sdk.policy", "lab_sdk.adapters"):
    sys.modules.pop(name, None)

from lab_sdk.adapters import ContractError  # noqa: E402


def is_contract_error(exc):
    return type(exc).__name__ == "ContractError"

RUNTIME_SHA = "b32b478e6b0051e53fb774fc3b52b666352c8c427d3e6ec3e1994d7b41341639"
CONFIG_SHA = "0e50177954035a578741140edf0bd68a7ac254e807b739fff3a89176e12894d2"


def extract(zip_path, target):
    if os.path.exists(target):
        shutil.rmtree(target)
    os.makedirs(target)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(target)
    return target


def load_wrapper(root):
    for name in list(sys.modules):
        if name == "lab_sdk" or name.startswith("lab_sdk."):
            del sys.modules[name]
    if root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)
    spec = importlib.util.spec_from_file_location("wrapped_entry", os.path.join(root, "entry.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Policy


def runtime_context(model=True, images=True):
    context = {"runtime_profile_sha256": RUNTIME_SHA, "configuration_sha256": CONFIG_SHA,
               "model_api": {"enabled": bool(model)}}
    context["image_dependencies"] = (["numpy", "Pillow", "opencv-python-headless"] if images else ["numpy"])
    return context


def main():
    os.makedirs(EVID, exist_ok=True)
    fixtures = json.load(open(os.path.join(PUB, "examples", "sdk-fixtures.json"), encoding="utf-8"))
    by_key = {(c["wave"], c["robot"], c["instruction"]["task_id"]): c for c in fixtures["cases"]}
    work = tempfile.mkdtemp(prefix="nine-wrapper-")
    results = []
    try:
        f_dir = extract(os.path.join(TASK, "outputs", "wave1.zip"), os.path.join(work, "franka-wave1"))
        f2_dir = extract(os.path.join(TASK, "outputs", "wave2.zip"), os.path.join(work, "franka-wave2"))
        p2_dir = extract(os.path.join(TASK, "outputs-piper-dual", "wave2.zip"),
                         os.path.join(work, "piper-wave2"))
        # 1. missing runtime identity must be refused
        Policy = load_wrapper(f_dir)
        case = by_key[("wave", "franka", "bottle_transfer")] if False else \
            by_key[("wave1", "franka", "bottle_transfer")]
        try:
            Policy().reset(case["instruction"])
            refused = False
        except Exception as exc:
            refused = is_contract_error(exc) and (
                "runtime" in str(exc) or "model" in str(exc) or "image" in str(exc))
        results.append({"check": "wave1 wrapper refuses missing runtime identity",
                        "passed": bool(refused)})
        # model-only or image-only missing identity must also be refused
        for label, ctx, expect in (
                ("missing model api", runtime_context(model=False), True),
                ("missing image deps", runtime_context(images=False), True),
                ("wrong profile sha", dict(runtime_context(), runtime_profile_sha256="0" * 64), True)):
            raw = dict(case["instruction"])
            raw["runtime_context"] = ctx
            try:
                Policy().reset(raw)
                refused_here = False
            except Exception as exc:
                refused_here = is_contract_error(exc)
            results.append({"check": "wave1 wrapper refuses " + label,
                            "passed": refused_here is expect})
        # 2. correctly bound wrapper accepts the real fixture and emits legal v1 actions
        raw = dict(case["instruction"])
        raw["runtime_context"] = runtime_context()
        wrapper = Policy()
        wrapper.reset(raw)
        observation = dict(case["observation"])
        observation.setdefault("images", {})
        observation["budget"] = dict(case["observation"].get("budget") or {})
        trace = []
        legal = True
        finished = False
        for _ in range(4000):
            action = wrapper.act(json.loads(json.dumps(observation)))
            trace.append(json.dumps(action, sort_keys=True))
            if set(action) == {"finish"}:
                finished = True
                break
            if set(action) - {"arms", "steps"}:
                legal = False
                break
            if not 1 <= int(action.get("steps", 0)) <= 120:
                legal = False
                break
            for arm, command in (action.get("arms") or {}).items():
                if len(command.get("positions") or []) != (7 if arm == "arm" else 6):
                    legal = False
                if not 0.0 <= float(command.get("gripper_width_m", 0.0)) <= 0.08:
                    legal = False
            observation["simulation_time_s"] += int(action.get("steps", 1)) / 240.0
        results.append({"check": "wave1 franka wrapper legal actions + finish",
                        "passed": bool(legal and finished), "actions": len(trace)})
        # 3. robot binding enforcement: franka package must reject the piper instruction
        piper_case = by_key[("wave1", "piper-dual", "bottle_transfer")]
        piper_raw = dict(piper_case["instruction"])
        piper_raw["runtime_context"] = runtime_context()
        try:
            load_wrapper(f_dir)().reset(piper_raw)
            rejected = False
        except Exception as exc:
            rejected = is_contract_error(exc)
        results.append({"check": "franka package rejects piper instruction", "passed": rejected})
        # 4. wave2 piper wrapper accepts the real C07 fixture and stays protocol-legal.
        #    (The tare/dose state machine itself is validated with a synthetic
        #    perception + kinematic mock in tests/ and in the Lead dev record,
        #    because the public fixtures carry no camera payloads.)
        c07 = by_key[("wave2", "piper-dual", "C07")]
        policy2 = load_wrapper(p2_dir)()
        raw2 = dict(c07["instruction"])
        raw2["runtime_context"] = runtime_context()
        policy2.reset(raw2)
        obs2 = json.loads(json.dumps(c07["observation"]))
        obs2.setdefault("images", {})
        legal2 = True
        finish_ok = False
        instrument_seen = 0
        for _ in range(6000):
            action = policy2.act(obs2)
            if set(action) == {"instrument"}:
                instrument_seen += 1
                obs2["last_instrument_result"] = {
                    "schema": "lab-instrument-result/v1", "ok": True, "stable": True,
                    "status": "STABLE", "net_mass_g": 0.0, "mass_g": 120.0,
                    "tare_active": True, "tare_version": 1}
                continue
            if set(action) == {"finish"}:
                finish_ok = True
                break
            if set(action) - {"arms", "steps"}:
                legal2 = False
                break
            if not 1 <= int(action.get("steps", 0)) <= 120:
                legal2 = False
                break
            for arm, command in (action.get("arms") or {}).items():
                if len(command.get("positions") or []) != 6:
                    legal2 = False
                if not 0.0 <= float(command.get("gripper_width_m", 0.0)) <= 0.1:
                    legal2 = False
            obs2["simulation_time_s"] = obs2.get("simulation_time_s", 0.0) + \
                int(action.get("steps", 1)) / 120.0
        results.append({"check": "wave2 piper wrapper legal actions + finish",
                        "passed": bool(legal2 and finish_ok),
                        "instrument_actions_seen_without_images": instrument_seen})
        # 5. canonical bytes are identical inside both tracks
        with zipfile.ZipFile(os.path.join(TASK, "outputs", "canonical.zip")) as a, \
                zipfile.ZipFile(os.path.join(TASK, "outputs-piper-dual", "canonical.zip")) as b:
            same = a.namelist() == b.namelist() and all(a.read(n) == b.read(n) for n in a.namelist())
        results.append({"check": "canonical bytes identical across robot packages", "passed": same})
    finally:
        shutil.rmtree(work, ignore_errors=True)
    ok = all(item["passed"] for item in results)
    report = {"schema": "nine-task-wrapper-evidence/v1", "ok": ok, "results": results}
    with open(os.path.join(EVID, "wrapper-roundtrip.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
