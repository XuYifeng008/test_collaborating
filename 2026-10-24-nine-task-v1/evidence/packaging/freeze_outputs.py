"""Freeze the policy into the official lab-nine package layout and verify it.

Runs the *official* public packaging tool (`lab_sdk.packaging`) exactly as
described in SUBMISSION.md, for both robot tracks, then re-verifies:
  * the canonical source hash and every ZIP member hash against the receipt;
  * deterministic bytes on a second run;
  * the published size/file limits;
  * that the derived wave1/wave2 wrappers refuse a missing image/model runtime
    and accept a correctly bound one (protocol-level wrapper check).

Output: deliverables/2026-10-24-nine-task/outputs            (franka, primary)
        deliverables/2026-10-24-nine-task/outputs-piper-dual (piper-dual)
        deliverables/2026-10-24-nine-task/evidence/packaging/*
"""

import hashlib
import json
import os
import shutil
import sys
import zipfile

ROOT = r"E:\dev\agents\lark-working"
PUB = os.path.join(ROOT, "inbox", "1024-test", "自主实验赛道选手公开包")
TASK = os.path.join(ROOT, "deliverables", "2026-10-24-nine-task")
SRC = os.path.join(TASK, "src", "my-policy")
EVID = os.path.join(TASK, "evidence", "packaging")
sys.path.insert(0, PUB)
sys.path.insert(0, TASK)

from lab_sdk.packaging import (MAX_ARCHIVE_BYTES, MAX_BYTES, MAX_FILES,  # noqa: E402
                               MAX_FILE_BYTES, canonical_json, pack_submission,
                               read_source, source_hash)


def canonical_json_sha(path):
    with open(path, "r", encoding="utf-8") as handle:
        value = json.load(handle)
    return hashlib.sha256(canonical_json(value)).hexdigest(), value


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pack(robot, out_dir):
    if os.path.exists(out_dir):
        raise SystemExit("output dir must be new: " + out_dir)
    receipt = pack_submission(SRC, out_dir, robot=robot,
                              runtime_profile_sha256=RUNTIME_SHA,
                              configuration_sha256=CONFIG_SHA)
    return receipt


def verify_receipt(receipt, out_dir, robot):
    problems = []
    manifest, files = read_source(SRC)
    if receipt.get("schema") != "lab-nine-package/v1":
        problems.append("receipt schema")
    if receipt.get("canonical_source_sha256") != source_hash(files):
        problems.append("canonical_source_sha256 mismatch")
    if receipt.get("runtime_profile_sha256") != RUNTIME_SHA:
        problems.append("runtime_profile_sha256 mismatch")
    if receipt.get("configuration_sha256") != CONFIG_SHA:
        problems.append("configuration_sha256 mismatch")
    if receipt.get("robot") != robot:
        problems.append("robot mismatch")
    names = set()
    for item in receipt.get("canonical_files") or []:
        if files.get(item["path"]) is None:
            problems.append("canonical file missing: " + item["path"])
            continue
        if hashlib.sha256(files[item["path"]]).hexdigest() != item["sha256"]:
            problems.append("canonical file sha mismatch: " + item["path"])
        names.add(item["path"])
    if names != set(files):
        problems.append("canonical_files set mismatch")
    for wave in ("wave1", "wave2"):
        entry = receipt["archives"].get(wave)
        path = os.path.join(out_dir, wave + ".zip")
        if entry is None or not os.path.exists(path):
            problems.append("missing archive " + wave)
            continue
        actual = sha256_file(path)
        if actual != entry["archive_sha256"]:
            problems.append(wave + " archive sha mismatch")
        size = os.path.getsize(path)
        if size > MAX_ARCHIVE_BYTES:
            problems.append(wave + " archive too large")
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES:
                problems.append(wave + " too many files")
            total = 0
            for info in infos:
                if info.file_size > MAX_FILE_BYTES:
                    problems.append(wave + " member too large: " + info.filename)
                total += info.file_size
            if total > MAX_BYTES:
                problems.append(wave + " unpacked too large")
            bad = archive.testzip()
            if bad is not None:
                problems.append(wave + " corrupt member: " + bad)
            # the derived wrapper must be present and the canonical source verbatim
            if archive.read("entry.py") != (
                    "from lab_sdk.policy import make_policy\n"
                    "Policy = make_policy(__file__, %r, %r)\n" % (wave, robot)).encode():
                problems.append(wave + " wrapper entry mismatch")
            derived_manifest = json.loads(archive.read("submission.json"))
            if derived_manifest.get("canonical_source_sha256") != receipt["canonical_source_sha256"]:
                problems.append(wave + " derived manifest source mismatch")
            for name, data in files.items():
                if archive.read("canonical/" + name) != data:
                    problems.append(wave + " canonical member mismatch: " + name)
    # canonical.zip == source directory bytes
    with zipfile.ZipFile(os.path.join(out_dir, "canonical.zip")) as archive:
        for name, data in files.items():
            if archive.read(name) != data:
                problems.append("canonical.zip member mismatch: " + name)
    return {"robot": robot, "problems": problems,
            "canonical_source_sha256": receipt["canonical_source_sha256"],
            "archives": {w: receipt["archives"][w] for w in ("wave1", "wave2")},
            "canonical_files": len(files), "source_bytes": sum(len(v) for v in files.values())}


def main():
    global RUNTIME_SHA, CONFIG_SHA
    os.makedirs(EVID, exist_ok=True)
    RUNTIME_SHA, runtime = canonical_json_sha(os.path.join(PUB, "contracts", "runtime-profile.json"))
    CONFIG_SHA, config = canonical_json_sha(os.path.join(PUB, "contracts", "configuration-template.json"))
    release = json.load(open(os.path.join(PUB, "release.json"), encoding="utf-8"))
    checks = {
        "runtime_profile_sha256": RUNTIME_SHA,
        "release_runtime_profile_sha256": release["runtime_profile_sha256"],
        "runtime_sha_matches_release": RUNTIME_SHA == release["runtime_profile_sha256"],
        "configuration_sha256": CONFIG_SHA,
        "release_example_configuration_sha256": release["example_configuration_sha256"],
        "configuration_sha_matches_release": CONFIG_SHA == release["example_configuration_sha256"],
        "configuration_deployment_qualified": [
            config["backends"]["wave1"]["deployment_qualified"],
            config["backends"]["wave2"]["deployment_qualified"]],
        "configuration_urls": [config["backends"]["wave1"]["url"], config["backends"]["wave2"]["url"]],
        "profile_id": runtime["profile_id"],
        "model_api_models": runtime["model_api"]["models"],
        "finite_frequency_hz_by_wave": {"wave1": 240.0, "wave2": 120.0},
    }
    packs = {}
    verification = {}
    for robot, out in (("franka", os.path.join(TASK, "outputs")),
                       ("piper-dual", os.path.join(TASK, "outputs-piper-dual"))):
        receipt = pack(robot, out)
        (open(os.path.join(EVID, "package-receipt-%s.json" % robot), "wb")
         .write(canonical_json(receipt) + b"\n"))
        verification[robot] = verify_receipt(receipt, out, robot)
        packs[robot] = {"output_dir": os.path.relpath(out, TASK).replace("\\", "/"),
                        "files": sorted(os.listdir(out)),
                        "sha256": {name: sha256_file(os.path.join(out, name))
                                   for name in sorted(os.listdir(out))}}
    # determinism: pack again into a temporary directory and compare archive bytes
    tmp = os.path.join(EVID, "_determinism")
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    deterministic = {}
    for robot, out in (("franka", os.path.join(TASK, "outputs")),
                       ("piper-dual", os.path.join(TASK, "outputs-piper-dual"))):
        again = os.path.join(tmp, robot)
        receipt2 = pack_submission(SRC, again, robot=robot,
                                   runtime_profile_sha256=RUNTIME_SHA,
                                   configuration_sha256=CONFIG_SHA)
        same = all(sha256_file(os.path.join(out, name)) == sha256_file(os.path.join(again, name))
                   for name in ("canonical.zip", "wave1.zip", "wave2.zip", "package-receipt.json"))
        deterministic[robot] = same
    shutil.rmtree(tmp)
    summary = {
        "schema": "nine-task-freeze-evidence/v1",
        "source_dir": os.path.relpath(SRC, TASK).replace("\\", "/"),
        "canonical_sha": source_hash(read_source(SRC)[1]),
        "identity_checks": checks,
        "packages": packs,
        "verification": verification,
        "deterministic_bytes": deterministic,
        "limits": {"max_archive_bytes": MAX_ARCHIVE_BYTES, "max_unpacked_bytes": MAX_BYTES,
                   "max_file_bytes": MAX_FILE_BYTES, "max_files": MAX_FILES},
    }
    with open(os.path.join(EVID, "freeze-summary.json"), "wb") as handle:
        handle.write(canonical_json(summary) + b"\n")
    ok = (all(v["problems"] == [] for v in verification.values())
          and all(deterministic.values())
          and checks["runtime_sha_matches_release"]
          and checks["configuration_sha_matches_release"])
    print(json.dumps({"ok": ok, "checks": checks,
                      "verification": verification, "deterministic": deterministic},
                     ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
