#!/usr/bin/env python3
"""Independent verification of the invitation-pilot evidence (Python stdlib only).

Usage:
    python verify_results.py

Checks every accepted receipt / final result pair in this directory against the
public result contract used by lab_eval.py, without importing organizer code.
Exits 0 and prints ALL CHECKS PASSED on success, 1 otherwise.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

CASES = [
    # stem, robot, scope, planned total
    ("franka-smoke", "franka", "smoke", 4),
    ("franka-full", "franka", "full", 20),
    ("dual_piper-full", "dual_piper", "full", 20),
]

TASK_IDS = [
    "bottle_transfer",
    "beaker_place",
    "balance_load",
    "stirrer_knob",
    "tube_insert",
]


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def load(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def main():
    archive_sha = hashlib.sha256((HERE / "idle.zip").read_bytes()).hexdigest()
    summary = load("summary.json")
    summary_by_id = {item["evaluation_id"]: item for item in summary["evaluations"]}
    source_hashes = set()

    for stem, robot, scope, planned in CASES:
        receipt = load(f"{stem}-accepted.json")
        envelope = load(f"{stem}-result.json")
        result = envelope["result"]
        eval_id = result["evaluation_id"]

        # 1) result digest (canonical JSON, not the pretty-printed envelope)
        digest = hashlib.sha256(canonical(result)).hexdigest()
        assert digest == envelope["result_sha256"], f"{stem}: result_sha256 mismatch"

        # 2) identity / plan / hashes vs accepted receipt
        for field in (
            "evaluation_id",
            "source_sha256",
            "archive_sha256",
            "robot",
            "scope",
            "planned_count",
        ):
            assert result[field] == receipt[field], f"{stem}: receipt {field} mismatch"
        assert receipt["robot"] == robot and receipt["scope"] == scope, f"{stem}: plan mismatch"
        assert receipt["planned_count"] == planned, f"{stem}: receipt planned_count"

        # 3) uploaded ZIP bytes vs receipt
        assert receipt["archive_sha256"] == archive_sha, f"{stem}: archive_sha256 vs idle.zip"
        source_hashes.add(result["source_sha256"])

        # 4) final-state contract
        assert result["state"] == "scored", f"{stem}: state"
        assert result["scoreIsFinal"] is True, f"{stem}: scoreIsFinal"
        assert result["scored"] is True, f"{stem}: scored"
        assert result["physical_evaluation"] is True, f"{stem}: physical_evaluation"
        assert result["competition_ready"] is False, f"{stem}: competition_ready"
        assert result["seed_randomizes_layout"] is False, f"{stem}: seed_randomizes_layout"
        expected_scope = "single_task_smoke" if scope == "smoke" else "five_task_track"
        assert result["score_scope"] == expected_scope, f"{stem}: score_scope"
        assert result["planned_count"] == planned, f"{stem}: planned_count"
        assert result["scored_count"] == planned, f"{stem}: scored_count"

        # 5) task / trial structure and arithmetic
        tasks = result["tasks"]
        assert len(tasks) == planned // 4, f"{stem}: task count"
        ids = [task["task_id"] for task in tasks]
        if scope == "full":
            assert ids == TASK_IDS, f"{stem}: task ids"
        else:
            assert ids[0] in TASK_IDS and len(ids) == 1, f"{stem}: smoke task id"
        for task in tasks:
            assert task["state"] == "complete", f"{stem}/{task['task_id']}: task state"
            assert task["planned_count"] == 4 and task["scored_count"] == 4
            trials = task["trials"]
            assert len(trials) == 4, f"{stem}/{task['task_id']}: trial count"
            assert len({t["trial_id"] for t in trials}) == 4, "trial ids must be distinct"
            assert all(t["state"] == "scored" for t in trials), "unscored trial"
            assert all(t["error_code"] is None for t in trials), "trial error_code"
            assert all(type(t["reward"]) in (int, float) and t["reward"] in (0, 1) for t in trials)
            mean = sum(t["reward"] for t in trials) / 4
            assert task["mean_reward"] == mean, f"{stem}/{task['task_id']}: mean mismatch"
        overall = sum(task["mean_reward"] for task in tasks) / len(tasks)
        assert result["mean_reward"] == overall, f"{stem}: overall mean"
        assert result["score_100"] == 100 * overall, f"{stem}: score_100"

        # 6) summary.json cross-check
        entry = summary_by_id[eval_id]
        assert entry["robot"] == robot and entry["scope"] == scope
        assert entry["state"] == "scored" and entry["scoreIsFinal"] is True
        assert entry["planned_count"] == planned and entry["scored_count"] == planned
        assert entry["result_sha256"] == envelope["result_sha256"]
        assert entry["mean_reward"] == result["mean_reward"]
        assert entry["score_100"] == result["score_100"]

        print(
            f"[ok] {eval_id}  robot={robot} scope={scope} "
            f"scored={result['scored_count']}/{result['planned_count']} "
            f"mean_reward={result['mean_reward']} score_100={result['score_100']}"
        )

    assert len(source_hashes) == 1, "source_sha256 differs between evaluations"
    assert summary["source_sha256"] == source_hashes.pop(), "summary source_sha256 mismatch"
    assert summary["archive"]["archive_sha256"] == archive_sha, "summary archive_sha256 mismatch"
    print(f"[ok] archive_sha256 {archive_sha}")
    print(f"[ok] source_sha256 {summary['source_sha256']}")
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"CHECK FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
