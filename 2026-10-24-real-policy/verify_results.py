"""Offline verification of the 2026-10-24 real-policy evaluation campaign.

Reads every accepted receipt / final result pair in ./evidence, recomputes the
canonical result digest and the per-task arithmetic, and records valid final
scores as well as the infrastructure `requires_review` outcomes and graded
policy failures (POLICY_TIMEOUT).  Standard library only.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVID = HERE / "evidence"
TASK_IDS = ["bottle_transfer", "beaker_place", "balance_load", "stirrer_knob", "tube_insert"]

# stem, robot, scope, kind ('final' or 'review')
CASES = [
    ("bottle-smoke", "dual_piper", "smoke", "final"),
    ("bottle-full", "dual_piper", "full", "final"),
    ("stirrer-smoke", "dual_piper", "smoke", "final"),
    ("stirrer2-smoke", "dual_piper", "smoke", "final"),
    ("stirrer3-smoke", "dual_piper", "smoke", "final"),
    ("combined-full", "dual_piper", "full", "final"),
    ("franka-bottle-smoke", "franka", "smoke", "review"),
    ("franka-bottle-smoke2", "franka", "smoke", "review"),
    ("franka-idle2", "franka", "smoke", "final"),
    ("franka-probe", "franka", "smoke", "final"),
    ("franka-probe2", "franka", "smoke", "final"),
    ("franka-probe3", "franka", "smoke", "final"),
    ("franka-probe4", "franka", "smoke", "final"),
    ("franka-stirrer-smoke", "franka", "smoke", "final"),
    ("franka-full", "franka", "full", "final"),
]


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def load(name):
    return json.loads((EVID / name).read_text(encoding="utf-8"))


def verify_envelope(receipt, envelope):
    result = envelope["result"]
    assert hashlib.sha256(canonical(result)).hexdigest() == envelope["result_sha256"], "result digest"
    for f in ("evaluation_id", "source_sha256", "archive_sha256", "robot", "scope", "planned_count"):
        assert result[f] == receipt[f], f"receipt field {f}"
    return result


def verify_final(receipt, envelope):
    result = verify_envelope(receipt, envelope)
    assert result["state"] == "scored", result["state"]
    assert result["scoreIsFinal"] is True and result["scored"] is True and result["physical_evaluation"] is True
    expected = 4 if result["scope"] == "smoke" else 20
    assert result["planned_count"] == expected == result["scored_count"]
    tasks = result["tasks"]
    assert len(tasks) == expected // 4
    ids = [t["task_id"] for t in tasks]
    if result["scope"] == "full":
        assert ids == TASK_IDS
    else:
        assert ids[0] in TASK_IDS
    for task in tasks:
        trials = task["trials"]
        assert task["state"] == "complete" and task["planned_count"] == 4 and task["scored_count"] == 4
        assert len(trials) == 4 and len({t["trial_id"] for t in trials}) == 4
        assert all(t["state"] == "scored" for t in trials)
        assert all(t["error_code"] in (None, "POLICY_TIMEOUT") for t in trials)
        assert all(type(t["reward"]) in (int, float) and t["reward"] in (0, 1) for t in trials)
        assert task["mean_reward"] == sum(t["reward"] for t in trials) / 4
    mean = sum(t["mean_reward"] for t in tasks) / len(tasks)
    assert result["mean_reward"] == mean and result["score_100"] == 100 * mean
    expected_scope = "single_task_smoke" if result["scope"] == "smoke" else "five_task_track"
    assert result["score_scope"] == expected_scope
    return result


def verify_review(receipt, envelope):
    result = verify_envelope(receipt, envelope)
    assert result["state"] == "requires_review"
    assert result["scoreIsFinal"] is False and result["scored"] is False
    assert result["physical_evaluation"] is False
    assert result["scored_count"] == 0
    codes = set()
    for task in result["tasks"]:
        assert task["scored_count"] == 0
        for trial in task["trials"]:
            assert trial["state"] == "pending" and trial["reward"] is None
            assert trial["outcome"] == "infrastructure_error"
            codes.add(trial["error_code"])
    assert codes == {"NATIVE_REQUIRES_REVIEW"}, codes
    return result


def main():
    summary = {"campaign": "2026-10-24 real-policy (colleague-test-01)", "evaluations": []}
    for stem, robot, scope, kind in CASES:
        receipt_path = EVID / f"{stem}-accepted.json"
        result_path = EVID / f"{stem}-result.json"
        if not receipt_path.exists() or not result_path.exists():
            print(f"[skip] {stem}: evidence not present yet")
            continue
        receipt = load(f"{stem}-accepted.json")
        envelope = load(f"{stem}-result.json")
        result = (verify_final if kind == "final" else verify_review)(receipt, envelope)
        entry = {
            "stem": stem,
            "kind": kind,
            "evaluation_id": result["evaluation_id"],
            "robot": result["robot"],
            "scope": result["scope"],
            "state": result["state"],
            "scoreIsFinal": result["scoreIsFinal"],
            "scored_count": result["scored_count"],
            "planned_count": result["planned_count"],
            "score_scope": result["score_scope"],
            "mean_reward": result["mean_reward"],
            "score_100": result["score_100"],
            "source_sha256": result["source_sha256"],
            "archive_sha256": result["archive_sha256"],
            "result_sha256": envelope["result_sha256"],
            "tasks": [
                {
                    "task_id": task["task_id"],
                    "mean_reward": task["mean_reward"],
                    "rewards": [t.get("reward") for t in task["trials"]],
                    "error_codes": [t.get("error_code") for t in task["trials"]],
                    "outcomes": [t.get("outcome") for t in task["trials"]],
                }
                for task in result["tasks"]
            ],
        }
        summary["evaluations"].append(entry)
        if kind == "final":
            print(f"[ok] {stem:22s} {result['evaluation_id']}  {result['robot']}/{result['scope']}  "
                  f"state={result['state']}  scored={result['scored_count']}/{result['planned_count']}  "
                  f"mean={result['mean_reward']}  score_100={result['score_100']}")
        else:
            print(f"[ok] {stem:22s} {result['evaluation_id']}  {result['robot']}/{result['scope']}  "
                  f"state=requires_review  infra_error=NATIVE_REQUIRES_REVIEW  trials=0/4 scored")

    (HERE / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote summary.json")
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
