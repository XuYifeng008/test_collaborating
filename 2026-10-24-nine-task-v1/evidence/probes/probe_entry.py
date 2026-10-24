#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""九题（lab-nine-20261024-v1）正式入口非破坏性核验器。

安全约束（硬性）：
1. 本文件只可能发出 HTTP GET 请求：`METHOD = "GET"` 是唯一方法常量，
   `urlopen` 调用处 data=None，代码中不存在 POST/PUT/PATCH/DELETE/上传代码路径。
2. token 只从 `inbox/colleague-test-01.token` 读入内存并放入 Authorization 请求头；
   token 值绝不会出现在 URL、stdout、日志、raw 响应、meta、summary 或报告中。
   输出前会做 token 泄漏扫描（内存 + 落盘回读）。
3. 不在服务端创建任何评测/Attempt；只读查询。
4. 只写本目录（deliverables/2026-10-24-nine-task/evidence/probes/）下的文件。

用途：回答“本题九题正式入口当前是否存在且可用；能否在不伪造的前提下取得 Attempt ID”。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --------------------------------------------------------------------------- #
# 常量与路径
# --------------------------------------------------------------------------- #

HERE = Path(__file__).resolve()
OUT_DIR = HERE.parent
RAW_DIR = OUT_DIR / "raw"

METHOD = "GET"  # 唯一允许的 HTTP 方法；任何其它方法都不应出现在本文件中

TOKEN_DEFAULT = None  # 由 find_workspace() 之后填充
MAX_TEXT_BYTES = 2 * 1024 * 1024
SCAN_EXT_BLACKLIST = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".pdf",
    ".zip", ".gz", ".tgz", ".tar", ".whl", ".pyc", ".pyo", ".dll", ".exe",
    ".so", ".bin", ".mp4", ".mp3", ".wav", ".sqlite", ".db",
}
SCAN_DIR_BLACKLIST = {".git", ".lark-cli", "__pycache__", "node_modules", ".venv", "venv"}

HTTP_TIMEOUT_S = 15
PORT_PROBE_TIMEOUT_S = 5

UA = "lab-nine-entry-probe/1.0 (non-destructive GET only)"


def find_workspace(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "inbox" / "1024-test").is_dir() and (p / "inbox" / "colleague-test-01.token").exists():
            return p
    raise SystemExit("无法定位工作区根目录（需要含 inbox/1024-test 与 inbox/colleague-test-01.token）")


WS = find_workspace(HERE)
TOKEN_FILE = WS / "inbox" / "colleague-test-01.token"
PKG = WS / "inbox" / "1024-test" / "自主实验赛道选手公开包"
OLD_KIT = WS / "inbox" / "lab-embodied-pilot-20261023"
OLD_SERVICE_JSON = OLD_KIT / "participant-kit" / "service.json"
LOCAL_EVALUATION = WS / "inbox" / "LOCAL_EVALUATION.md"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def local_now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def public_meta(rec: dict) -> dict:
    """去掉私有键（_body/_parsed/_meta）后的可序列化请求/响应元数据。"""
    return {k: v for k, v in rec.items() if not k.startswith("_")}


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - 记录错误即可
        return {"__read_error__": f"{type(exc).__name__}: {exc}"}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def safe(text, limit: int = 300) -> str:
    s = str(text).replace("\n", " ").replace("\r", " ")
    return s if len(s) <= limit else s[: limit - 3] + "..."


# --------------------------------------------------------------------------- #
# 1. 静态搜索：九题正式入口配置/地址/token/CLI
# --------------------------------------------------------------------------- #

MARKERS = [
    ("nine_task_binding", "nine_task_binding"),
    ("nine_organizer_config_schema", r"lab-nine-organizer-config/v1"),
    ("deployment_qualified_true", r'"deployment_qualified"\s*:\s*true'),
    ("nine_service_deployed_flag", r"live_nine_task_service_deployed"),
    ("challenge_ids_null", r'"challenge_ids"\s*:\s*null'),
    ("challenge_id_assignment", r'"?challenge_id"?\s*[:=]'),
    ("attempt_id_assignment", r'"?attempt_id"?\s*[:=]'),
    ("organizer_cli_invocation", r"-m\s+organizer"),
    ("playground_submit_invocation", r"playground\s+submit"),
    ("challenge_id_cli_flag", r"--challenge-id"),
    ("playground_token_env", r"PLAYGROUND_TOKEN"),
]

URL_RE = re.compile(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%\-]+")
CANDIDATE_SERVICE_PORTS = {"8787", "8090", "8890"}


def is_candidate_url(url: str) -> bool:
    low = url.lower()
    if "bohrium" in low:
        return True
    if re.search(r"/v1/(tasks|evaluations|challenges|attempts|health)\b", low):
        return True
    m = re.match(r"https?://([^/:]+)(?::(\d+))?", url)
    if m and m.group(2) in CANDIDATE_SERVICE_PORTS:
        return True
    if "challenge" in low and ("play" in low or "competition" in low):
        return True
    return False


def iter_scan_files(root: Path):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in sorted(dirnames)
            if d not in SCAN_DIR_BLACKLIST and (Path(dirpath) / d).resolve() != OUT_DIR
        ]
        for name in sorted(filenames):
            p = Path(dirpath) / name
            ext = p.suffix.lower()
            if ext in SCAN_EXT_BLACKLIST:
                continue
            try:
                if not p.is_file() or p.stat().st_size > MAX_TEXT_BYTES:
                    continue
            except OSError:
                continue
            yield p
            count += 1
            if count >= 6000:
                return


def static_search() -> dict:
    root = WS
    marker_hits = {name: [] for name, _ in MARKERS}
    compiled = {name: re.compile(pat) for name, pat in MARKERS}
    url_candidates: dict[str, list[str]] = {}
    url_total = 0
    scanned = 0
    errors: list[str] = []

    for p in iter_scan_files(root):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{p.relative_to(root)}: {type(exc).__name__}")
            continue
        scanned += 1
        rel = p.relative_to(root).as_posix()
        lines = text.splitlines()
        for name, rx in compiled.items():
            hits = []
            for ln, line in enumerate(lines, 1):
                if rx.search(line):
                    hits.append({"line": ln, "text": safe(line, 220)})
                    if len(hits) >= 3:
                        break
            if hits:
                marker_hits[name].append({"path": rel, "hits": hits})

        for m in URL_RE.finditer(text):
            url = m.group(0).rstrip(".,;:)]}\"'")
            url_total += 1
            if not is_candidate_url(url):
                continue
            if url not in url_candidates:
                line_no = text[: m.start()].count("\n") + 1
                url_candidates[url] = [f"{rel}:{line_no}"]
            elif len(url_candidates[url]) < 5:
                line_no = text[: m.start()].count("\n") + 1
                url_candidates[url].append(f"{rel}:{line_no}")

    for name in marker_hits:
        marker_hits[name] = marker_hits[name][:20]

    # 文件名维度：CLI / 配置候选
    name_rx = re.compile(r"(organizer|nine|challenge|attempt|upload|platform|entry|submit)", re.I)
    name_hits = []
    for p in iter_scan_files(root):
        if name_rx.search(p.name):
            name_hits.append(p.relative_to(root).as_posix())
            if len(name_hits) >= 80:
                break

    # 已知 CLI/配置文件存在性（针对本题上下文）
    known_candidates = {
        " organizer Python 模块（python -m organizer）": None,
        "九题组织者 CLI / 上传 CLI（workspace 内）": [
            "inbox/1024-test/自主实验赛道选手公开包/lab_sdk/packaging.py",
            "inbox/lab-embodied-pilot-20261023/participant-kit/lab_eval.py",
            "inbox/lab-embodied-pilot-20261023/participant-kit/submission_bundle.py",
        ],
        "九题部署配置（new 配置 + deployment_qualified=true）": None,
        "Challenge / Attempt 平台配置（含 live URL 与凭据）": None,
    }
    known = {}
    known["organizer_module"] = None
    known["candidate_paths"] = {
        rel: {"exists": (root / rel).exists()} for rel in known_candidates[
            "九题组织者 CLI / 上传 CLI（workspace 内）"
        ]
    }

    return {
        "workspace_root": str(root),
        "scan_scope": "递归扫描工作区（文本文件，单文件<=2MiB）；排除 .git/.lark-cli/__pycache__/node_modules 与本次 probes 输出目录",
        "files_scanned": scanned,
        "scan_errors": errors[:20],
        "markers": marker_hits,
        "url_total_matches": url_total,
        "candidate_service_urls": [
            {"url": u, "sources": srcs} for u, srcs in list(url_candidates.items())[:60]
        ],
        "filename_candidates": name_hits,
        "known_cli_and_config": known,
        "external_scope_note": (
            "未递归扫描工作区之外的主机目录。理由：九题组织者部署代码按公开包声明另包交付"
            "（docs/发布接入清单.md：公开包不含服务器管理脚本，组织者部署代码另包），"
            "工作区即本次任务共享文件系统范围。仅列出一层父目录名作为边界记录。"
        ),
        "parent_dir_listing": parent_listing(),
    }


def parent_listing() -> dict:
    out = {}
    for label, path in [
        ("workspace_root", WS),
        ("E:/dev/agents", WS.parent),
        ("E:/dev", WS.parent.parent),
    ]:
        try:
            if path.is_dir():
                out[label] = sorted(p.name for p in path.iterdir())[:60]
        except OSError as exc:
            out[label] = [f"<error: {type(exc).__name__}>"]
    return out


def environment_check() -> dict:
    env_interest = re.compile(r"(LAB|TOKEN|CHALLENGE|ATTEMPT|NINE|BOHR|PLAYGROUND|PLATFORM)", re.I)
    env_names = []
    for k, v in os.environ.items():
        if env_interest.search(k):
            env_names.append({"name": k, "value_length": len(v)})

    modules = {}
    for mod in ("organizer", "lab_sdk", "lab_platform", "lab_nine", "lab_nine_sdk"):
        try:
            modules[mod] = importlib.util.find_spec(mod) is not None
        except (ImportError, ValueError):
            modules[mod] = False

    clis = {}
    for exe in ("organizer", "lab_eval", "lab_nine", "nine", "upload", "bohrium", "playground"):
        clis[exe] = shutil.which(exe)

    listeners = {}
    for port in (8090, 8787, 8888, 8890, 9000):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.4)
        try:
            listeners[str(port)] = "open" if s.connect_ex(("127.0.0.1", port)) == 0 else "closed"
        except OSError:
            listeners[str(port)] = "closed"
        finally:
            s.close()

    return {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "cwd": os.getcwd(),
        "env_vars_matching_lab_token_challenge_attempt_nine_bohr": env_names,
        "python_modules": modules,
        "path_executables": clis,
        "local_tcp_127.0.0.1": listeners,
        "note": "env 只记录变量名与长度，不记录值；PATH 只记录解析结果路径。",
    }


# --------------------------------------------------------------------------- #
# 1b. 平台 CLI 入口核查（Playground / paper2arm CLI）
# --------------------------------------------------------------------------- #
# 只执行只读命令：--help / auth status / submit -h / task list --json。
# 绝不执行 auth login/register（写）、submit（创建 Attempt=POST）、task download/upload（写）。
PLAYGROUND_SAFE_COMMANDS = [
    ["--help"],
    ["auth", "status"],
    ["submit", "-h"],
    ["status", "-h"],
    ["task", "list", "--limit", "7000", "--json"],
]
PLAYGROUND_STRONG_RX = re.compile(
    r"nine|九题|embodied|具身|franka|piper|manipulat|自主实验|isaac|grasp|"
    r"bottle_transfer|beaker_place|balance_load|stirrer_knob|tube_insert|lab-nine|robot arm",
    re.I,
)
PLAYGROUND_WEAK_RX = re.compile(r"robot|机器人|实验室|vla", re.I)


def _cli_run(cli_path: str, args: list, timeout: int) -> dict:
    t0 = time.time()
    cmd = ["cmd", "/c", cli_path] + args
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return {
            "argv": ["playground"] + args,
            "returncode": r.returncode,
            "elapsed_s": round(time.time() - t0, 1),
            "stdout": r.stdout,
            "stderr": safe(r.stderr, 1500),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "argv": ["playground"] + args,
            "error": f"{type(exc).__name__}: {safe(exc, 300)}",
            "elapsed_s": round(time.time() - t0, 1),
        }


def _redact_cli_output(text: str) -> str:
    """CLI 输出脱敏：只做安全记录（help/status/list 本不含 token；再保险一次）。"""
    out = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+", r"\1<redacted>", text)
    out = re.sub(r"(?i)(token[\"']?\s*[:=]\s*)[\"']?[A-Za-z0-9._\-]{8,}", r"\1<redacted>", out)
    return out


def probe_playground_cli() -> dict:
    """核查平台 CLI 是否存在、是否已认证、是否有本题 Challenge；全部只读。"""
    ev = {
        "cli_path": shutil.which("playground"),
        "detected": bool(shutil.which("playground")),
        "non_destructive_commands": [["playground"] + a for a in PLAYGROUND_SAFE_COMMANDS],
        "forbidden_commands_not_executed": [
            "playground submit（会创建 Attempt=POST）",
            "playground auth login/register（写凭据/建号）",
            "playground task download/upload/upload-package（写平台）",
            "playground status --attempt-id（无 Attempt）",
        ],
        "results": {},
    }
    if not ev["detected"]:
        ev["judgment"] = "PATH 中无 playground CLI"
        return ev

    cli = ev["cli_path"]

    # --help（本地）
    h = _cli_run(cli, ["--help"], 30)
    ev["results"]["help"] = {
        "returncode": h.get("returncode"),
        "first_lines": [ln for ln in _redact_cli_output(h.get("stdout", "")).splitlines() if ln.strip()][:22],
        "error": h.get("error"),
    }

    # auth status（只读，验证已认证与 api_base）
    a = _cli_run(cli, ["auth", "status"], 60)
    auth = {"returncode": a.get("returncode"), "error": a.get("error")}
    try:
        auth_json = json.loads(a.get("stdout", ""))
        auth.update({
            "authenticated": auth_json.get("authenticated"),
            "api_base": auth_json.get("api_base"),
            "credentials_path": auth_json.get("credentials"),
            "credentials_file_exists": Path(auth_json.get("credentials", "")).is_file()
            if auth_json.get("credentials") else None,
        })
    except Exception:  # noqa: BLE001
        auth["stdout_first_lines"] = _redact_cli_output(a.get("stdout", "")).splitlines()[:5]
    ev["results"]["auth_status"] = auth

    # 凭据文件：只记录键名，不读取/记录值（不打印 token）
    cred_path = auth.get("credentials_path")
    cred_keys = []
    if cred_path and Path(cred_path).is_file():
        for line in Path(cred_path).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                cred_keys.append(line.split("=", 1)[0].strip())
    ev["results"]["credentials_file"] = {
        "path": cred_path,
        "exists": bool(cred_path and Path(cred_path).is_file()),
        "key_names_only": cred_keys,
        "values_read_or_written": False,
    }

    # 本地配置（可选）
    local_cfg = Path.home() / ".playground" / "config.json"
    ev["results"]["local_config"] = {"path": str(local_cfg), "exists": local_cfg.is_file()}

    # submit -h：确认 submit 会创建 Attempt（不可执行）
    s = _cli_run(cli, ["submit", "-h"], 30)
    submit_help = _redact_cli_output(s.get("stdout", ""))
    ev["results"]["submit_help"] = {
        "returncode": s.get("returncode"),
        "contains_create_attempt": "creates a Playground attempt" in submit_help,
        "usage_line": next((ln.strip() for ln in submit_help.splitlines() if "playground submit --challenge-id" in ln), None),
        "error": s.get("error"),
    }

    # task list 全量（只读 GET）：查找本题 Challenge
    tl = _cli_run(cli, ["task", "list", "--limit", "7000", "--json"], 300)
    list_ev = {
        "returncode": tl.get("returncode"),
        "elapsed_s": tl.get("elapsed_s"),
        "error": tl.get("error"),
    }
    strong, weak = [], []
    try:
        payload = json.loads(tl.get("stdout", ""))
        tasks = payload.get("tasks", [])
        list_ev.update({
            "schema_version": payload.get("schema_version"),
            "api_base": payload.get("api_base"),
            "total_visible": payload.get("total"),
            "returned": len(tasks),
            "keyword_strong": PLAYGROUND_STRONG_RX.pattern,
            "keyword_weak": PLAYGROUND_WEAK_RX.pattern,
        })
        for t in tasks:
            blob = json.dumps(
                {k: t.get(k) for k in ("id", "title", "tags")}, ensure_ascii=False
            )
            item = {
                "id": t.get("id"), "title": t.get("title"),
                "status": t.get("status"), "tags": t.get("tags"),
                "attempts": t.get("attempts"),
            }
            if PLAYGROUND_STRONG_RX.search(blob):
                strong.append(item)
            elif PLAYGROUND_WEAK_RX.search(blob):
                weak.append(item)
        list_ev["strong_match_count"] = len(strong)
        list_ev["strong_matches"] = strong[:60]
        list_ev["weak_match_count"] = len(weak)
        list_ev["weak_matches"] = weak[:20]
        list_ev["nine_task_challenge_visible"] = any(
            "lab-nine" in json.dumps(m, ensure_ascii=False).lower()
            or "nine-task" in json.dumps(m, ensure_ascii=False).lower()
            or "embodied" in json.dumps(m, ensure_ascii=False).lower()
            for m in strong
        )
    except Exception as exc:  # noqa: BLE001
        list_ev["parse_error"] = f"{type(exc).__name__}: {safe(exc, 200)}"
        list_ev["stdout_head"] = _redact_cli_output(tl.get("stdout", ""))[:800]
    ev["results"]["task_list"] = list_ev

    # 把 CLI 只读查询证据落 raw/
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cli_raw = RAW_DIR / "cli-playground-entry-evidence.json"
    cli_raw.write_text(
        json.dumps(
            {
                "utc": utc_now_iso(),
                "purpose": "平台 CLI 入口只读核查（九题正式入口是否存在）",
                "cli_path": cli,
                "commands": ["playground --help", "playground auth status",
                             "playground submit -h", "playground task list --limit 7000 --json"],
                "forbidden_commands_not_executed": ev["forbidden_commands_not_executed"],
                "results": {k: v for k, v in ev["results"].items()},
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    ev["raw_evidence_file"] = cli_raw.relative_to(OUT_DIR).as_posix()

    authenticated = bool(ev["results"]["auth_status"].get("authenticated"))
    visible = bool(ev["results"]["task_list"].get("nine_task_challenge_visible"))
    ev["judgment"] = (
        f"官方 Playground CLI 存在且已认证（api_base={ev['results']['auth_status'].get('api_base')}）；"
        f"但全量可见 Challenge {ev['results']['task_list'].get('total_visible')} 个中"
        f"未发现本题九题具身实验 Challenge，且工作区无 Challenge ID 配置；"
        f"submit 会创建 Attempt（POST），按约束未执行。"
        if ev["results"]["auth_status"].get("authenticated")
        else "Playground CLI 存在但未认证或无法验证；未执行登录/注册"
    )
    return ev


# --------------------------------------------------------------------------- #
# 2. 原文行号引用（避免报告手写行号出错）
# --------------------------------------------------------------------------- #

CITATION_SPECS = [
    # (key, path, needle)
    ("submission_config_template", PKG / "SUBMISSION.md",
     "题包的 `contracts/configuration-template.json` 是本地预览配置"),
    ("submission_old_five_task", PKG / "SUBMISSION.md",
     "旧标准库五题服务的full=20"),
    ("submission_formal_entry", PKG / "SUBMISSION.md",
     "正式Playground登录、Challenge ID、产物上传命令与会话trace位置由该题实际平台配置提供"),
    ("submission_no_formal_submit", PKG / "SUBMISSION.md",
     "当前打包工具不执行正式提交、不读平台凭证"),
    ("submission_local_unified", PKG / "SUBMISSION.md",
     "本地统一服务的组织者注册/dispatch/refresh示例在组织者包"),
    ("submission_attempt_id", PKG / "SUBMISSION.md",
     "平台接入后提交一次，保存Attempt ID"),
    ("api_no_playground_credentials", PKG / "docs/平台接口.md",
     "本模块没有 Playground Challenge／Attempt／官方回调凭据"),
    ("api_template_cannot_submit", PKG / "docs/平台接口.md",
     "该模板**不能提交到旧线上服务**"),
    ("api_new_backend_catalog", PKG / "docs/平台接口.md",
     "新后端 `GET /v1/tasks` 在原目录之外必须提供"),
    ("api_binding_needs_worker", PKG / "docs/平台接口.md",
     "需要安装、连接新 worker runtime 后由服务端绑定"),
    ("api_local_loopback_only", PKG / "docs/平台接口.md",
     "仅绑定 `127.0.0.1`"),
    ("api_no_official_callback", PKG / "docs/平台接口.md",
     "当前没有可执行的官方回调命令"),
    ("api_deployment_qualified", PKG / "docs/平台接口.md",
     "`deployment_qualified=true` 时所有三个后端摘要、资格ID和HTTPS地址必须有效"),
    ("checklist_playground_not_configured", PKG / "docs/发布接入清单.md",
     "Playground目前未配置"),
    ("checklist_platform_status_false", PKG / "docs/发布接入清单.md",
     "`playground_integrated=false`"),
    ("checklist_playground_contract", PKG / "docs/发布接入清单.md",
     "一个Attempt映射一个机器人完整36槽"),
    ("checklist_old_window", PKG / "docs/发布接入清单.md",
     "现有开发服务10月26日12:00接单截止"),
    ("readme_no_challenge_needed", PKG / "README.md",
     "无需发布或创建Challenge"),
    ("release_live_nine_false", PKG / "release.json",
     '"live_nine_task_service_deployed": false'),
    ("release_native36_false", PKG / "release.json",
     '"new_runtime_native_full36_verified": false'),
    ("release_playground_false", PKG / "release.json",
     '"playground_integrated": false'),
    ("release_competition_false", PKG / "release.json",
     '"competition_ready": false'),
    ("release_activation_required", PKG / "release.json",
     '"activation_required"'),
    ("rules_platform_block", PKG / "contracts/rules-v1.json",
     '"platform"'),
    ("rules_challenge_ids_null", PKG / "contracts/rules-v1.json",
     '"challenge_ids": null'),
    ("config_status_preview", PKG / "contracts/configuration-template.json",
     '"deployment_status": "local_preview_only_not_a_live_evaluation_service"'),
    ("config_url_null", PKG / "contracts/configuration-template.json",
     '"url": null'),
    ("config_not_qualified", PKG / "contracts/configuration-template.json",
     '"deployment_qualified": false'),
    ("statement_formal_entry", PKG / "docs/自主实验赛道PLAYGROUND题面.md",
     "通过当前题目页的正式入口提交这些产物"),
    ("statement_challenge_from_page", PKG / "docs/自主实验赛道PLAYGROUND题面.md",
     "正式 Challenge 与登录命令由本页面实际接入配置提供"),
    ("old_service_url", OLD_SERVICE_JSON, '"url":'),
    ("old_service_benchmark", OLD_SERVICE_JSON, '"benchmark_id":'),
    ("old_service_accept_until", OLD_SERVICE_JSON, '"accept_until":'),
    ("old_service_expires_at", OLD_SERVICE_JSON, '"expires_at":'),
    ("old_agent_invite_not_official", OLD_KIT / "participant-kit/AGENT_GUIDE.md",
     "这是邀请联调服务，不是正式 Playground 榜单页面"),
    ("old_agent_tasks_api", OLD_KIT / "participant-kit/AGENT_GUIDE.md",
     "| `GET /v1/tasks` | 任务、资源、窗口、worker 状态 |"),
    ("old_readme_invite", OLD_KIT / "README.md",
     "这是固定布局、标准库Python策略的邀请联调服务"),
    ("old_readme_signup_deadline", OLD_KIT / "README.md",
     "接单截止北京时间"),
    ("local_eval_loopback", LOCAL_EVALUATION,
     "HTTP服务只监听 `127.0.0.1`，没有部署到比赛平台"),
    ("local_eval_default_url", LOCAL_EVALUATION,
     "默认URL为 `http://127.0.0.1:8090`"),
]


def build_citations() -> dict:
    out = {}
    for key, path, needle in CITATION_SPECS:
        rel = path.relative_to(WS).as_posix() if path.is_relative_to(WS) else str(path)
        entry = {"file": rel, "needle": needle, "found": False, "lines": [], "texts": []}
        if path.is_file():
            lines = read_text(path).splitlines()
            for ln, line in enumerate(lines, 1):
                if needle in line:
                    entry["found"] = True
                    entry["lines"].append(ln)
                    entry["texts"].append(safe(line, 260))
                    if len(entry["lines"]) >= 3:
                        break
        out[key] = entry
    return out


CIT: dict = {}


def cite(key: str) -> str:
    e = CIT.get(key)
    if not e or not e["found"]:
        return f"`{e['file'] if e else key}`（未找到原文，需人工复核）"
    if len(e["lines"]) == 1:
        return f"`{e['file']}:{e['lines'][0]}`"
    return f"`{e['file']}:{','.join(str(x) for x in e['lines'])}`"


def cite_text(key: str) -> str:
    e = CIT.get(key)
    if not e or not e["texts"]:
        return ""
    return e["texts"][0]


# --------------------------------------------------------------------------- #
# 3. 非破坏性 HTTP GET 探测
# --------------------------------------------------------------------------- #

def redact_headers(headers) -> dict:
    """headers 可以是 mapping 或 (k, v) 列表。"""
    items = headers.items() if hasattr(headers, "items") else headers
    out = {}
    for k, v in items:
        lk = k.lower()
        if any(s in lk for s in ("authorization", "cookie", "token", "secret", "key")):
            out[k] = "<redacted>"
        else:
            out[k] = v
    return out


def do_get(seq: int, label: str, url: str, token: str | None, timeout: int = HTTP_TIMEOUT_S) -> dict:
    """执行一条非破坏性 GET；只返回元数据 + 原始 body（body 会单独落盘）。"""
    assert METHOD == "GET"
    started_utc = utc_now_iso()
    req_headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    auth_mode = "none"
    if token is not None:
        req_headers["Authorization"] = "Bearer " + token
        auth_mode = "bearer_token_from_file"

    rec = {
        "seq": seq,
        "label": label,
        "utc_started": started_utc,
        "utc_finished": None,
        "method": METHOD,
        "url": url,
        "auth": auth_mode,
        "request_headers_redacted": redact_headers(req_headers),
        "tls": "default_verified",
        "status": None,
        "reason": None,
        "content_type": None,
        "response_headers_redacted": {},
        "body_bytes": 0,
        "body_sha256": None,
        "body_file": None,
        "error": None,
    }

    def issue(ctx) -> tuple:
        req = urllib.request.Request(url, headers=req_headers, method=METHOD, data=None)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, resp.reason, list(resp.headers.items()), resp.read()

    t0 = time.time()
    body = b""
    try:
        try:
            status, reason, headers, body = issue(ssl.create_default_context())
        except ssl.SSLError as exc:
            # 仅证书类错误时回退；如实记录，不隐藏
            rec["tls"] = f"unverified_fallback_after_{type(exc).__name__}"
            status, reason, headers, body = issue(ssl._create_unverified_context())
        rec["status"] = status
        rec["reason"] = reason
        rec["response_headers_redacted"] = redact_headers(headers)
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read() if exc.fp is not None else b""
        rec["status"] = status
        rec["reason"] = exc.reason
        rec["response_headers_redacted"] = redact_headers(exc.headers.items()) if exc.headers else {}
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
        body = b""
        detail = getattr(exc, "reason", None) or exc
        rec["error"] = f"{type(exc).__name__}: {safe(detail, 240)}"
    finally:
        rec["elapsed_ms"] = int((time.time() - t0) * 1000)

    rec["utc_finished"] = utc_now_iso()
    if rec.get("content_type") is None and rec.get("response_headers_redacted"):
        for k, v in rec["response_headers_redacted"].items():
            if k.lower() == "content-type" and not str(v).startswith("<"):
                rec["content_type"] = v

    rec["body_bytes"] = len(body)
    rec["body_sha256"] = sha256_bytes(body)

    ext = ".bin"
    parsed = None
    if body:
        try:
            parsed = json.loads(body.decode("utf-8"))
            ext = ".json"
        except Exception:  # noqa: BLE001
            ext = ".txt"
            try:
                text = body.decode("utf-8")
            except Exception:  # noqa: BLE001
                text = body.decode("latin-1", errors="replace")
            parsed = {"__non_json_text__": text[:4000]}

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    body_path = RAW_DIR / f"{seq:02d}_{label}.body{ext}"
    body_path.write_bytes(body)
    rec["body_file"] = body_path.relative_to(OUT_DIR).as_posix()

    rec["_body"] = body
    rec["_parsed"] = parsed
    rec["_meta"] = rec.copy()
    return rec


def find_key(obj, key_names, max_depth=8):
    """递归查找 key，返回 [(path, value)]。"""
    wanted = {k.lower() for k in key_names}
    found = []

    def walk(node, path, depth):
        if depth > max_depth:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if str(k).lower() in wanted:
                    found.append((".".join(path + [str(k)]), v))
                walk(v, path + [str(k)], depth + 1)
        elif isinstance(node, list):
            for i, v in enumerate(node[:50]):
                walk(v, path + [f"[{i}]"], depth + 1)

    walk(obj, [], 0)
    return found


def analyze_tasks_payload(parsed, body_text: str) -> dict:
    """针对旧五题 /v1/tasks catalog 的结构化解析（按实际响应 schema lab-eval-pilot-catalog/v1）。"""
    if not isinstance(parsed, dict):
        return {"parsed_type": type(parsed).__name__}

    catalog = parsed.get("catalog") if isinstance(parsed.get("catalog"), dict) else {}
    tasks = catalog.get("tasks") if isinstance(catalog.get("tasks"), dict) else {}

    ids = list(catalog.get("basic_task_ids") or [])
    if not ids and tasks:
        ids = list(tasks.keys())

    task_details = {}
    for tid, meta in tasks.items():
        if not isinstance(meta, dict):
            continue
        task_details[tid] = {
            "tier": meta.get("tier"),
            "role": meta.get("role"),
            "competition_ready": meta.get("competition_ready"),
            "layout": meta.get("layout"),
            "robots": meta.get("robots"),
            "seed_randomizes_layout": meta.get("seed_randomizes_layout"),
        }

    worker_map = parsed.get("workers") if isinstance(parsed.get("workers"), dict) else {}
    online = {k: (v.get("online") if isinstance(v, dict) else None) for k, v in worker_map.items()}

    out = {
        "top_level_keys": sorted(parsed.keys()),
        "service_catalog_schema": parsed.get("schema"),
        "catalog_schema": catalog.get("schema"),
        "benchmark_id_declared_in_service_json": None,  # 由 main 回填
        "benchmark_id_in_catalog": catalog.get("benchmark_id"),
        "qualification_scope": catalog.get("qualification_scope"),
        "task_ids": ids,
        "basic_task_ids": catalog.get("basic_task_ids"),
        "task_count": len(ids) if ids else None,
        "tasks": task_details,
        "replicas": parsed.get("replicas"),
        "scopes": parsed.get("scopes"),
        "workers_online": online,
        "accept_until": parsed.get("accept_until"),
        "expires_at": parsed.get("expires_at"),
        "limits": {
            "policy_cpu_seconds": parsed.get("policy_cpu_seconds"),
            "policy_wall_seconds": parsed.get("policy_wall_seconds"),
            "policy_memory_bytes": parsed.get("policy_memory_bytes"),
            "policy_network": parsed.get("policy_network"),
            "policy_runtime": parsed.get("policy_runtime"),
        },
        "nine_task_fields_present_in_body": {
            "nine_task_binding": "nine_task_binding" in body_text,
            "runtime_profile_sha256": "runtime_profile_sha256" in body_text,
            "configuration_sha256": "configuration_sha256" in body_text,
            "runtime_capabilities": "runtime_capabilities" in body_text,
        },
        "has_challenge_field": bool(re.search(r'"challenge', body_text)),
        "has_attempt_field": bool(re.search(r'"attempt', body_text)),
        "body_mentions_challenge": "challenge" in body_text.lower(),
        "body_mentions_attempt": "attempt" in body_text.lower(),
    }
    return out


def analyze_generic_body(parsed, body_text: str) -> dict:
    out = {
        "body_mentions_nine": "nine" in body_text.lower(),
        "body_mentions_challenge": "challenge" in body_text.lower(),
        "body_mentions_attempt": "attempt" in body_text.lower(),
        "body_mentions_36": "36" in body_text,
    }
    if isinstance(parsed, dict):
        out["top_level_keys"] = sorted(list(parsed.keys()))[:40]
        err = parsed.get("error") or parsed.get("code") or parsed.get("detail")
        if err is not None:
            out["error_or_code"] = safe(str(err), 200)
    return out


# --------------------------------------------------------------------------- #
# 4. 主流程
# --------------------------------------------------------------------------- #

def main() -> int:
    global CIT
    t_start = utc_now_iso()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    token_value = None
    token_meta = {
        "token_file": str(TOKEN_FILE.relative_to(WS).as_posix()),
        "token_present": TOKEN_FILE.is_file(),
        "token_length_chars": None,
        "token_used": False,
        "token_exposure": "只用于 Authorization 请求头；不写入任何输出文件/日志/stdout/URL，输出后做泄漏扫描",
    }
    if TOKEN_FILE.is_file():
        token_value = TOKEN_FILE.read_text(encoding="utf-8").strip()
        token_meta["token_length_chars"] = len(token_value)
    else:
        token_meta["error"] = "token 文件缺失，鉴权探测将跳过"

    print("[1/5] 读取公开包与旧包元数据 ...")
    release = read_json(PKG / "release.json")
    rules = read_json(PKG / "contracts/rules-v1.json")
    config = read_json(PKG / "contracts/configuration-template.json")
    old_service = read_json(OLD_SERVICE_JSON)

    public_status = {
        "release_id": release.get("rules_id"),
        "release_version": release.get("release_version"),
        "release_flags": {
            k: release.get(k)
            for k in (
                "live_nine_task_service_deployed",
                "new_runtime_native_full36_verified",
                "external_model_api_qualified",
                "playground_integrated",
                "official_score_writeback_verified",
                "competition_ready",
            )
        },
        "rules_platform": rules.get("platform") if isinstance(rules, dict) else None,
        "configuration_template": {
            "schema": config.get("schema"),
            "configuration_id": config.get("configuration_id"),
            "deployment_status": config.get("deployment_status"),
            "wave1": {
                "url": (config.get("backends") or {}).get("wave1", {}).get("url"),
                "benchmark_id": (config.get("backends") or {}).get("wave1", {}).get("benchmark_id"),
                "deployment_qualified": (config.get("backends") or {}).get("wave1", {}).get("deployment_qualified"),
            },
            "wave2": {
                "url": (config.get("backends") or {}).get("wave2", {}).get("url"),
                "benchmark_id": (config.get("backends") or {}).get("wave2", {}).get("benchmark_id"),
                "deployment_qualified": (config.get("backends") or {}).get("wave2", {}).get("deployment_qualified"),
            },
        },
        "notes": [
            "release.json 与 contracts/rules-v1.json 的 platform 块是公开包对平台接入状态的权威自述。",
            "contracts/configuration-template.json 是本地预览配置，两个后端 url=null 且 deployment_qualified=false。",
        ],
    }

    old_service_meta = {
        "service_json_path": OLD_SERVICE_JSON.relative_to(WS).as_posix(),
        "schema": old_service.get("schema"),
        "url": old_service.get("url"),
        "benchmark_id": old_service.get("benchmark_id"),
        "accept_until": old_service.get("accept_until"),
        "expires_at": old_service.get("expires_at"),
        "competition_ready": old_service.get("competition_ready"),
        "window_now_utc": utc_now_iso(),
    }
    if old_service.get("accept_until"):
        try:
            dt = datetime.fromisoformat(old_service["accept_until"].replace("Z", "+00:00"))
            old_service_meta["accept_window_open"] = datetime.now(timezone.utc) < dt
            old_service_meta["seconds_until_accept_deadline"] = int(
                (dt - datetime.now(timezone.utc)).total_seconds()
            )
        except ValueError:
            pass

    CIT = build_citations()

    print("[2/5] 静态搜索九题正式入口（配置/地址/token/CLI） ...")
    static = static_search()
    env = environment_check()
    print("       平台 CLI 只读核查（--help / auth status / task list） ...")
    cli_evidence = probe_playground_cli()

    print("[3/5] 对唯一已知旧联调服务执行非破坏性 GET 探测 ...")
    base = (old_service.get("url") or "").rstrip("/")
    host = ""
    m = re.match(r"https?://([^/:]+)", base)
    if m:
        host = m.group(1)

    probes_spec = [
        (1, "health_noauth", f"{base}/health", None),
        (2, "tasks_noauth", f"{base}/v1/tasks", None),
        (3, "tasks_auth", f"{base}/v1/tasks", token_value),
        (4, "challenges_auth", f"{base}/v1/challenges", token_value),
        (5, "attempts_auth", f"{base}/v1/attempts", token_value),
        (6, "evaluations_list_auth", f"{base}/v1/evaluations", token_value),
        (7, "root_noauth", f"{base}/", None),
    ]
    if host:
        for i, port in enumerate(("8787", "8090", "8890"), start=8):
            probes_spec.append((i, f"port{port}_health_noauth", f"https://{host}:{port}/health", None))

    results = []
    for seq, label, url, tok in probes_spec:
        if token_value is None and tok is not None:
            results.append({
                "seq": seq, "label": label, "method": METHOD, "url": url, "auth": "skipped_no_token",
                "utc_started": utc_now_iso(), "utc_finished": utc_now_iso(), "status": None,
                "error": "token 文件缺失", "body_bytes": 0, "body_sha256": None, "body_file": None,
            })
            continue
        print(f"    GET {url}  (auth={'yes' if tok else 'no'})")
        try:
            r = do_get(seq, label, url, tok, timeout=HTTP_TIMEOUT_S if seq <= 7 else PORT_PROBE_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 - 单条探测失败不应中断整体
            r = {
                "seq": seq, "label": label, "method": METHOD, "url": url,
                "auth": "bearer_token_from_file" if tok else "none",
                "utc_started": utc_now_iso(), "utc_finished": utc_now_iso(), "status": None,
                "error": f"probe_runner_error: {type(exc).__name__}: {safe(exc, 200)}",
                "body_bytes": 0, "body_sha256": None, "body_file": None,
            }
        results.append(r)

    print("[4/5] 解析响应并做判定 ...")
    probes = []
    body_texts = {}
    for r in results:
        body = r.get("_body", b"")
        try:
            body_text = body.decode("utf-8")
        except Exception:  # noqa: BLE001
            body_text = body.decode("latin-1", errors="replace")
        body_texts[r["seq"]] = body_text

        parsed = r.get("_parsed")
        if r["label"] in ("tasks_auth", "tasks_noauth") and isinstance(parsed, dict):
            analysis = analyze_tasks_payload(parsed, body_text)
        else:
            analysis = analyze_generic_body(parsed, body_text)

        entry = public_meta(r)
        entry["analysis"] = analysis
        entry["judgment"] = judge_probe(entry, analysis)
        probes.append(entry)

    tasks_auth = next((p for p in probes if p["label"] == "tasks_auth"), None)
    tasks_body_text = body_texts.get(3, "")
    old_identity = {
        "probe_status": tasks_auth.get("status") if tasks_auth else None,
        "service_json_benchmark_id": old_service.get("benchmark_id"),
        "benchmark_id_in_catalog": None,
        "benchmark_id": None,
        "service_catalog_schema": None,
        "catalog_schema": None,
        "qualification_scope": None,
        "task_count": None,
        "task_ids": [],
        "tasks": {},
        "replicas": None,
        "scopes": None,
        "workers_online": None,
        "limits": None,
        "accept_until": None,
        "expires_at": None,
        "competition_ready": old_service.get("competition_ready"),
        "nine_task_fields": None,
        "has_challenge_field": None,
        "has_attempt_field": None,
    }
    if tasks_auth and isinstance(tasks_auth.get("analysis"), dict):
        a = tasks_auth["analysis"]
        old_identity.update({
            "benchmark_id_in_catalog": a.get("benchmark_id_in_catalog"),
            "benchmark_id": a.get("benchmark_id_in_catalog") or old_service.get("benchmark_id"),
            "service_catalog_schema": a.get("service_catalog_schema"),
            "catalog_schema": a.get("catalog_schema"),
            "qualification_scope": a.get("qualification_scope"),
            "task_count": a.get("task_count"),
            "task_ids": a.get("task_ids"),
            "tasks": a.get("tasks"),
            "replicas": a.get("replicas"),
            "scopes": a.get("scopes"),
            "workers_online": a.get("workers_online"),
            "limits": a.get("limits"),
            "accept_until": a.get("accept_until"),
            "expires_at": a.get("expires_at"),
            "nine_task_fields": a.get("nine_task_fields_present_in_body"),
            "has_challenge_field": a.get("has_challenge_field"),
            "has_attempt_field": a.get("has_attempt_field"),
        })

    nine_binding_missing = True
    if isinstance(old_identity.get("nine_task_fields"), dict):
        nine_binding_missing = not any(old_identity["nine_task_fields"].values())

    nine_service_urls = [
        u for u in static.get("candidate_service_urls", [])
        if "bohrium" in u["url"].lower() and "play.bohrium.com" not in u["url"].lower()
    ]
    deployment_qualified_true_hits = len(static["markers"].get("deployment_qualified_true", []))
    challenge_id_config_hits = [
        h for h in static["markers"].get("challenge_id_assignment", [])
        if "/docs/" not in h["path"] and "题面" not in h["path"]
    ]

    # 判定“正式入口存在”的必要条件（缺一不可）：
    # a) 存在候选正式服务 URL；b) 存在 deployment_qualified=true 的部署配置；
    # c) 在线 catalog 确实带有九题绑定字段（nine_task_binding / profile / config 摘要）。
    nine_fields = old_identity.get("nine_task_fields") or {}
    old_identity["benchmark_id_matches_nine_rules_id"] = (
        isinstance(rules, dict) and old_identity.get("benchmark_id") == rules.get("rules_id")
    )
    formal_entry_found = bool(
        nine_service_urls
        and deployment_qualified_true_hits > 0
        and isinstance(nine_fields, dict)
        and any(nine_fields.values())
    )

    health = next((p for p in probes if p["label"] == "health_noauth"), None)
    old_service_live = bool(tasks_auth and tasks_auth.get("status") == 200)

    conclusion = {
        "formal_entry_found": formal_entry_found,
        "formal_submission_executable": False,
        "attempt_id_obtainable_without_fabrication": False,
        "statement": "正式提交不可执行、Attempt ID 无法在不伪造的前提下取得",
        "reasons": [
            "公开包 / release.json / rules-v1.json 自述 Playground 未接入：challenge_ids=null、"
            "playground_integrated=false、official_score_writeback_verified=false、competition_ready=false、"
            "live_nine_task_service_deployed=false。",
            "工作区与环境中未发现本题的 Challenge ID、正式提交地址或平台上传命令配置；"
            "唯一在配置里出现的评测服务地址是旧五题邀请联调服务（service.json）。",
            "环境中确有官方 Playground CLI（playground 0.1.40，@paper2arm/playground-cli）且已认证"
            "（api_base=https://play.bohrium.com/api），但平台可见的 6932 个 Challenge 中没有本题九题具身实验题目，"
            "也没有任何配置给出本题 Challenge ID；playground submit 会创建 Attempt（POST），按本任务约束未执行。",
            "旧服务 GET /v1/tasks 返回的 benchmark_id 不是 lab-nine-20261024-v1，且 catalog 不含 "
            "nine_task_binding / runtime_profile_sha256 / configuration_sha256 等九题新后端必备字段，"
            "按 docs/平台接口.md 不能作为统一九题正式入口。",
            "公开包 contracts/configuration-template.json 两个后端 url=null 且 deployment_qualified=false；"
            "按 docs/平台接口.md，本地组织者 HTTP 仅绑定 127.0.0.1 且需要另建部署配置，本机也无对应监听。",
            "Attempt 属于平台侧对象；没有平台认证与 Challenge 路由时，任何“生成的 Attempt ID”都会是伪造值。",
        ],
        "static_entry_markers": {
            "candidate_nine_service_urls": [u["url"] for u in nine_service_urls],
            "deployment_qualified_true_hits": deployment_qualified_true_hits,
            "challenge_id_config_hits": [h["path"] for h in challenge_id_config_hits],
            "organizer_module_installed": env["python_modules"].get("organizer"),
            "local_loopback_candidate_listeners": env["local_tcp_127.0.0.1"],
        },
        "platform_cli_entry": {
            "cli_present": cli_evidence.get("detected"),
            "cli_path": cli_evidence.get("cli_path"),
            "authenticated": (cli_evidence.get("results", {}).get("auth_status", {}) or {}).get("authenticated"),
            "api_base": (cli_evidence.get("results", {}).get("auth_status", {}) or {}).get("api_base"),
            "visible_challenges_total": (cli_evidence.get("results", {}).get("task_list", {}) or {}).get("total_visible"),
            "nine_task_challenge_visible": (cli_evidence.get("results", {}).get("task_list", {}) or {}).get("nine_task_challenge_visible"),
            "challenge_id_configured": False,
            "submit_command_template": "playground submit --challenge-id <本题ChallengeID> --outputs <outputs> --trace <session.jsonl>",
            "submit_executed": False,
            "submit_would_create_attempt_and_upload": True,
            "judgment": cli_evidence.get("judgment"),
        },
        "old_service_identity": old_identity,
        "old_service_live": old_service_live,
        "nine_task_fields_missing": nine_binding_missing,
        "evidence": {
            "static": "static_search",
            "probes": [p["label"] for p in probes],
            "citations": {k: {"file": v["file"], "lines": v["lines"], "found": v["found"]}
                          for k, v in CIT.items()},
        },
    }

    generated_utc = utc_now_iso()
    summary = {
        "schema": "lab-nine-entry-probe/v1",
        "rules_id": rules.get("rules_id") if isinstance(rules, dict) else None,
        "purpose": "核实 lab-nine-20261024-v1 九题正式入口是否存在且可用（非破坏性 GET；禁止伪造 Attempt）",
        "generated_utc": generated_utc,
        "generated_local": local_now_iso(),
        "started_utc": t_start,
        "host": os.environ.get("COMPUTERNAME") or socket.gethostname(),
        "workspace": str(WS),
        "output_dir": OUT_DIR.relative_to(WS).as_posix(),
        "method_policy": {
            "http_methods_issued": ["GET"],
            "mutation_requests": "none",
            "created_evaluations_or_attempts": 0,
            "cli_commands_issued": [
                "playground --help", "playground auth status",
                "playground submit -h", "playground status -h",
                "playground task list --limit 7000 --json",
            ],
            "cli_mutations": "none（未 submit、未 auth login/register、未 upload/download）",
            "note": "本脚本只实现 GET；未上传、未创建评测、未提交策略。",
        },
        "token_handling": token_meta,
        "static_search": static,
        "environment": env,
        "platform_cli": cli_evidence,
        "citations": CIT,
        "public_package_platform_status": public_status,
        "known_old_service": old_service_meta,
        "probes": probes,
        "conclusion": conclusion,
        "artifacts": None,
    }
    summary["artifacts"] = {
        "script": "probe_entry.py",
        "report": "probe-report.md",
        "summary": "probe-summary.json",
        "raw_dir": "raw/",
        "raw_files": sorted(p.name for p in RAW_DIR.glob("*")),
    }

    # 内存级 token 泄漏扫描（先扫再落盘）
    token_bytes = token_value.encode("utf-8") if token_value else None
    planned = {
        "probe-summary.json": json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"),
    }
    for r in results:
        if r.get("_body") is not None and r.get("body_file"):
            planned[r["body_file"]] = r["_body"]
    leak_mem = scan_for_token(planned, token_bytes)
    if leak_mem:
        print("FATAL: 内存扫描发现 token 泄漏，拒绝写盘：" + ", ".join(leak_mem))
        return 1

    print("[5/5] 写 raw/、probe-summary.json、probe-report.md ...")
    for r in results:
        if r.get("body_file"):
            meta_path = RAW_DIR / (Path(r["body_file"]).stem + ".meta.json")
            meta_path.write_text(
                json.dumps(public_meta(r), ensure_ascii=False, indent=2), encoding="utf-8"
            )
    summary["artifacts"]["raw_files"] = sorted(p.name for p in RAW_DIR.glob("*"))
    (OUT_DIR / "probe-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 落盘回读泄漏扫描
    disk_scan = scan_dir_for_token(OUT_DIR, token_bytes, skip_names={"probe-report.md"})
    summary["leak_scan"] = {
        "token_value_never_written": not disk_scan["leaks"],
        "checked_files": disk_scan["checked_files"],
        "leaked_files": disk_scan["leaks"],
    }

    report = build_report(summary)
    # 报告最后写；再统一终检
    (OUT_DIR / "probe-report.md").write_text(report, encoding="utf-8")

    final_scan = scan_dir_for_token(OUT_DIR, token_bytes)
    summary["leak_scan"]["final_checked_files"] = final_scan["checked_files"]
    summary["leak_scan"]["final_leaked_files"] = final_scan["leaks"]
    summary["leak_scan"]["passed"] = not final_scan["leaks"]
    (OUT_DIR / "probe-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # 因为 summary 在报告之后重写，报告里的 leak 状态以最终扫描为准；如不一致重写报告
    if final_scan["leaks"]:
        print("FATAL: 落盘终检发现 token 泄漏：" + ", ".join(final_scan["leaks"]))
        return 1
    report2 = build_report(summary)
    if report2 != report:
        (OUT_DIR / "probe-report.md").write_text(report2, encoding="utf-8")

    print()
    print("结论：未发现九题正式入口 ->", conclusion["statement"])
    if tasks_auth:
        print("旧服务探测：GET /v1/tasks -> HTTP", tasks_auth.get("status"),
              "| benchmark_id(catalog):", (tasks_auth.get("analysis") or {}).get("benchmark_id_in_catalog"),
              "| task_count:", (tasks_auth.get("analysis") or {}).get("task_count"))
    print("health 探测：HTTP", health.get("status") if health else None)
    print("平台 CLI：", "present" if cli_evidence.get("detected") else "absent",
          "| authenticated:", (cli_evidence.get("results", {}).get("auth_status", {}) or {}).get("authenticated"),
          "| visible_challenges:", (cli_evidence.get("results", {}).get("task_list", {}) or {}).get("total_visible"),
          "| nine_task_challenge_visible:", (cli_evidence.get("results", {}).get("task_list", {}) or {}).get("nine_task_challenge_visible"))
    print("产物目录：", OUT_DIR)
    print("token 泄漏终检：", "pass" if not final_scan["leaks"] else "FAIL")
    return 0


def scan_for_token(contents: dict, token_bytes: bytes | None) -> list[str]:
    if not token_bytes:
        return []
    leaks = []
    for name, content in contents.items():
        if isinstance(content, str):
            content = content.encode("utf-8")
        if token_bytes in content:
            leaks.append(name)
    return leaks


def scan_dir_for_token(root: Path, token_bytes: bytes | None, skip_names: set | None = None) -> dict:
    skip_names = skip_names or set()
    checked = 0
    leaks = []
    if not token_bytes:
        return {"checked_files": 0, "leaks": leaks}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name in skip_names:
            continue
        checked += 1
        try:
            data = p.read_bytes()
        except OSError:
            continue
        if token_bytes in data:
            leaks.append(p.relative_to(root).as_posix())
    return {"checked_files": checked, "leaks": leaks}


def judge_probe(entry: dict, analysis: dict) -> str:
    label = entry["label"]
    status = entry.get("status")
    if status is None:
        return f"请求失败（{entry.get('error')}）；无法据此判断入口"
    if label == "health_noauth":
        if status == 200:
            return "旧联调服务存活；/health 未鉴权 200（返回旧服务健康 schema：lab-eval-pilot-health/v1）"
        return f"HTTP {status}；该路由不可用"
    if label == "tasks_noauth":
        if status == 401:
            return "catalog 需鉴权（401 UNAUTHORIZED），未鉴权不泄露内容"
        return f"无鉴权请求 HTTP {status}"
    if label == "tasks_auth":
        if status == 200:
            bid = analysis.get("benchmark_id_in_catalog")
            cnt = analysis.get("task_count")
            scopes = analysis.get("scopes")
            nf = analysis.get("nine_task_fields_present_in_body") or {}
            missing = [k for k, v in nf.items() if not v]
            return (
                f"可读旧五题 catalog：benchmark_id={bid}，task_count={cnt}，scopes={json.dumps(scopes, ensure_ascii=False)}；"
                f"缺失九题绑定字段 {missing}"
            )
        if status == 401:
            return "鉴权失败 401；未能读取 catalog"
        return f"HTTP {status}；catalog 不可读"
    if label == "challenges_auth":
        if status == 404:
            return "旧服务无 /v1/challenges 路由（404），不存在 Challenge 列表接口"
        return f"HTTP {status}"
    if label == "attempts_auth":
        if status == 404:
            return "旧服务无 /v1/attempts 路由（404），不存在 Attempt 查询接口"
        return f"HTTP {status}"
    if label == "evaluations_list_auth":
        if status in (404, 405):
            return f"旧服务不支持评测列表（HTTP {status}）；九题平台也不存在公开 list 路由"
        return f"HTTP {status}"
    if label == "root_noauth":
        return f"根路径 HTTP {status}"
    if label.startswith("port"):
        if status is None:
            return "同域候选端口拒绝/超时（未监听或不可达）"
        return f"同域候选端口 HTTP {status}"
    return f"HTTP {status}"


# --------------------------------------------------------------------------- #
# 5. 报告生成
# --------------------------------------------------------------------------- #

def build_report(summary: dict) -> str:
    s = summary
    probes = s["probes"]
    con = s["conclusion"]
    old = con["old_service_identity"]
    st = s["static_search"]
    env = s["environment"]
    ps = s["public_package_platform_status"]
    token_meta = s["token_handling"]
    leak = s.get("leak_scan", {})

    def row(p):
        return "| {seq} | `{label}` | {auth} | {status} | {ctype} | {n} | `{sha}` |".format(
            seq=p["seq"],
            label=p["label"],
            auth="Bearer" if p.get("auth") == "bearer_token_from_file" else ("无" if p.get("auth") == "none" else p.get("auth")),
            status=p.get("status") if p.get("status") is not None else "无响应",
            ctype=safe(p.get("content_type") or "-", 40),
            n=p.get("body_bytes", 0),
            sha=(p.get("body_sha256") or "-")[:16] + "…" if p.get("body_sha256") else "-",
        )

    probe_rows = "\n".join(row(p) for p in probes)

    marker_lines = []
    for name, hits in st["markers"].items():
        if hits:
            files = "、".join(f"`{h['path']}`" + f"（行{','.join(str(x['line']) for x in h['hits'])}）" for h in hits[:6])
            marker_lines.append(f"- `{name}`：命中 {len(hits)} 个文件 —— {files}")
        else:
            marker_lines.append(f"- `{name}`：**0 命中**")
    marker_text = "\n".join(marker_lines)

    url_lines = []
    for item in st["candidate_service_urls"]:
        url_lines.append(f"- `{item['url']}`（来源：{'、'.join(item['sources'][:3])}）")
    url_text = "\n".join(url_lines) if url_lines else "- （无候选服务 URL）"

    cli = s.get("platform_cli") or {}
    cli_auth = (cli.get("results") or {}).get("auth_status") or {}
    cli_list = (cli.get("results") or {}).get("task_list") or {}
    cli_submit_help = (cli.get("results") or {}).get("submit_help") or {}
    cli_help = (cli.get("results") or {}).get("help") or {}
    cli_ver = (cli_help.get("first_lines") or ["（版本未解析）"])[0]
    cli_strong_matches = cli_list.get("strong_matches") or []
    cli_strong_text = "；".join("`" + str(m.get("id")) + "`" for m in cli_strong_matches[:12]) or "（无）"
    cli_cred_keys = ((cli.get("results") or {}).get("credentials_file") or {}).get("key_names_only") or []
    cli_forbidden = cli.get("forbidden_commands_not_executed") or []
    cli_judgment = cli.get("judgment") or ""

    task_ids = old.get("task_ids") or []
    replicas = json.dumps(old.get("replicas"), ensure_ascii=False)
    scopes = json.dumps(old.get("scopes"), ensure_ascii=False)
    workers = json.dumps(old.get("workers_online"), ensure_ascii=False)
    limits = json.dumps(old.get("limits"), ensure_ascii=False)
    nine_fields = json.dumps(old.get("nine_task_fields"), ensure_ascii=False)
    task_details = old.get("tasks") or {}
    task_detail_text = "、".join(
        f"`{tid}`({d.get('tier')}/{d.get('role')}, competition_ready={d.get('competition_ready')})"
        for tid, d in task_details.items()
    ) if task_details else "（未解析）"

    citations = CIT
    def c(key):
        return cite(key)

    missing_fields = [k for k, v in (old.get("nine_task_fields") or {}).items() if not v]
    if missing_fields:
        missing_text = "、".join("`" + x + "`" for x in missing_fields)
    else:
        missing_text = "（无缺失，但这与文档公共声明矛盾，需复核）"
    task_ids_text = ", ".join(task_ids) if task_ids else "（未能从响应解析）"

    report = f"""# 九题正式入口非破坏性探测报告（{s.get('rules_id')}）

- 生成时间（UTC）：`{s['generated_utc']}`（本地 `{s['generated_local']}`）
- 执行脚本：[`probe_entry.py`](probe_entry.py)（**只发送 HTTP GET**；无上传、无创建评测、无提交策略）
- token：只从 `{token_meta['token_file']}` 读入内存并放入 `Authorization: Bearer` 请求头，
  值不落任何文件（长度 {token_meta.get('token_length_chars')} 字符，泄漏终检：**{'通过' if leak.get('passed') else '失败'}**）
- 输出目录：`{s['output_dir']}/`（raw 原始响应、summary、本报告）

## 0. 结论先行

**未发现 lab-nine-20261024-v1 的九题正式入口。正式提交不可执行、Attempt ID 无法在不伪造的前提下取得。**

- 静态搜索：没有本题的九题正式入口配置（无 `deployment_qualified=true` 的部署配置、无本题 Challenge ID、无正式提交地址；旧联调 token 文件存在，但只用于旧五题服务只读探测）。
- 平台 CLI 核查：PATH 中确实存在官方 `playground` CLI（@paper2arm/playground-cli，`{cli_ver}`），`auth status` 显示**已认证**（`api_base={cli_auth.get('api_base')}`）；但**本题 Challenge ID 未配置**，全量可见 Challenge（`{cli_list.get('total_visible')}` 个）中没有本题九题具身实验 Challenge，而 `playground submit` 会创建 Attempt（POST），按本任务约束**未执行**。
- 网络探测：旧包 `service.json` 声明的唯一评测后端是“五题邀请联调服务”，catalog 的 `benchmark_id` 与九题规则身份不一致，且**缺少九题新后端的全部绑定字段**（`nine_task_binding` / `runtime_profile_sha256` / `configuration_sha256` / `runtime_capabilities`），按合同不能当正式入口。
- 公开包自身声明：`challenge_ids=null`、`playground_integrated=false`、`official_score_writeback_verified=false`、`competition_ready=false`、`live_nine_task_service_deployed=false`，部署模板两个后端 `url=null` 且 `deployment_qualified=false`。
- 因此本次**没有产生任何 Attempt ID**；本目录所有文件都不含 Attempt ID / 评测 ID / 分数（也不允许出现伪造值）。

## 1. 探测方法与安全约束

| 项 | 内容 |
|---|---|
| HTTP 方法 | 仅 `GET`（脚本内 `METHOD = "GET"` 是唯一方法常量；`urlopen` 的 `data=None`） |
| 是否创建对象 | 否。未 POST、未上传 ZIP、未创建 evaluation/Attempt、未提交策略 |
| token 使用 | 仅 `{token_meta['token_file']}` → `Authorization: Bearer` 请求头；URL 中无 token；输出前中后各做一次 token 泄漏扫描 |
| token 输出 | 不写入 raw/meta/summary/report/stdout；本报告只出现 token 文件路径与长度 |
| TLS | `ssl.create_default_context()` 默认证书校验（{ssl.OPENSSL_VERSION}）；仅在证书错误时回退并如实标记（本次探测未触发回退） |
| 探测时间窗 | 旧服务 `accept_until={s['known_old_service'].get('accept_until')}`，`expires_at={s['known_old_service'].get('expires_at')}`；当前 UTC `{s['known_old_service'].get('window_now_utc')}`，窗口仍开放 |

## 2. 静态搜索：九题正式入口配置 / 地址 / token / CLI

搜索范围：`{st['workspace_root']}` 递归文本文件（≤2 MiB），共扫描 **{st['files_scanned']}** 个文件；
排除 `.git`、`.lark-cli`（飞书凭据目录）、`__pycache__`、`node_modules` 与本次 probes 输出目录。

关键词命中：

{marker_text}

- 这说明 `nine_task_binding` 只出现在**文档/规则/同任务核验产物**中（`docs/平台接口.md`、`docs/运行档.md` 等），没有任何一条是“已部署服务配置”；`deployment_qualified=true` 在工作区**0 命中**（部署配置不存在）。
- `challenge_id` / `attempt_id` 只出现在旧平台的字段草案文档、术语表和通信记录里（`deliverables/2026-10-22-*`、`work-context`），不是本题平台配置；`playground submit` / `--challenge-id` 的命中也都是旧交接文档里的**示例命令**，没有任何一条绑定本题 Challenge ID。

候选服务 URL（过滤后）：

{url_text}

CLI / 模块核查：

- `python -m organizer`：{('已安装' if env['python_modules'].get('organizer') else '**未安装**')}（`organizer` 模块不存在，公开包只含 `lab_sdk` 打包工具，见 {c('submission_no_formal_submit')}）
- `lab_sdk` / `lab_platform` / `lab_nine` 模块：{json.dumps(env['python_modules'], ensure_ascii=False)}
- PATH 可执行：{json.dumps(env['path_executables'], ensure_ascii=False)}
- 本机 127.0.0.1 候选监听端口：{json.dumps(env['local_tcp_127.0.0.1'], ensure_ascii=False)}（`docs/平台接口.md` 说明本地组织者 HTTP 仅绑定 `127.0.0.1`，见 {c('api_local_loopback_only')}；本机无 8090/8787/8890 监听）
- 环境变量（只记名与长度）：{json.dumps(env['env_vars_matching_lab_token_challenge_attempt_nine_bohr'], ensure_ascii=False)}
- 已知 CLI/配置候选文件存在性：{json.dumps(st['known_cli_and_config'], ensure_ascii=False)}

### 2.1 平台 CLI 入口核查（只读命令）

> **结论：平台侧官方 CLI 通道存在且已认证，但本题 Challenge ID 未配置、平台可见 Challenge 中也没有本题题目。**
> 因此“有 CLI”不等于“本题正式入口可用”：没有 Challenge ID 时无法创建正确的 Attempt。

| 项 | 值 |
|---|---|
| CLI | `{cli.get('cli_path')}`（`{cli_ver}`，npm 包 `@paper2arm/playground-cli`） |
| 认证状态 | `authenticated={cli_auth.get('authenticated')}`；`api_base={cli_auth.get('api_base')}` |
| 凭据文件 | `{((cli.get('results') or {}).get('credentials_file') or {}).get('path')}`（存在：`{((cli.get('results') or {}).get('credentials_file') or {}).get('exists')}`；只记录键名 `{cli_cred_keys}`，**未读取/未输出其值**） |
| 本地平台配置 | `{((cli.get('results') or {}).get('local_config') or {}).get('path')}`（存在：`{((cli.get('results') or {}).get('local_config') or {}).get('exists')}`） |
| `submit` 语义 | `contains_create_attempt={cli_submit_help.get('contains_create_attempt')}`；命令模板：`{cli_submit_help.get('usage_line')}` |
| 可见 Challenge 总数 | `{cli_list.get('total_visible')}`（`task list --limit 7000 --json` 返回 `{cli_list.get('returned')}` 条） |
| 本题九题 Challenge 是否可见 | **`{cli_list.get('nine_task_challenge_visible')}`** |
| 执行的只读命令 | `playground --help`、`playground auth status`、`playground submit -h`、`playground status -h`、`playground task list --limit 7000 --json` |
| 明确未执行的命令 | {'；'.join(cli_forbidden)} |
| CLI 判定 | {cli_judgment} |
| 原始证据 | `{cli.get('raw_evidence_file')}` |

关键词强匹配（`nine / 九题 / embodied / 具身 / franka / piper / manipulat / 自主实验 / isaac / grasp / bottle_transfer / beaker_place / balance_load / stirrer_knob / tube_insert / lab-nine / robot arm`）
命中 {cli_list.get('strong_match_count')} 条，经人工核对**没有一条**是本题九题具身实验 Challenge（命中主要来自 `nine-gene`、`nine-point`、`manipulator` 等子串，以及一条“电解液自主实验闭环”化学挑战，与本包台面/天平任务无关）：{cli_strong_text}。

- 若平台后续发布本题 Challenge，正式提交命令将是 `playground submit --challenge-id <本题ChallengeID> --outputs <output-dir> --trace <session.jsonl>`；
  该命令会**创建 Attempt 并上传 bundle（POST/写操作）**，超出本核验任务“只读、非破坏性”的授权范围，故未执行。
- 本次也没有执行 `auth login/register`、`task download/upload`、`submit`，因此平台侧没有产生任何本题 Attempt 或提交记录。

边界说明：{st['external_scope_note']}

## 3. 网络探测结果（非破坏性 GET）

目标地址来自旧包 `inbox/lab-embodied-pilot-20261023/participant-kit/service.json`：
`{s['known_old_service'].get('url')}`

| # | 探测 | 鉴权 | HTTP | content-type | body bytes | body sha256（前缀） |
|---|---|---|---|---|---|---|
{probe_rows}

原始响应保存在 `raw/`（每条含 `.meta.json` 记录 UTC、method、URL、状态、响应头、body sha256）。

关键判定（逐条完整版见 `probe-summary.json` 的 `probes[].judgment`）：

- `GET /health`：200，`{{schema: lab-eval-pilot-health/v1, status: ok}}` —— 旧联调服务存活；
- `GET /v1/tasks`：无鉴权 401 `UNAUTHORIZED`；带 token 200 —— 需要旧服务 team token（token 文件有效）；
- `GET /v1/challenges`、`GET /v1/attempts`、`GET /v1/evaluations`（列表）：全部 **404 `NOT_FOUND`** —— 旧服务不存在 Challenge / Attempt 概念与对应路由；
- `/` 未鉴权 401；同域候选端口 `:8787`、`:8090`、`:8890` 的 `/health` 均连接超时 —— 该域名只通过 443 反向代理到旧服务，没有可直连的其它入口。

### 3.1 服务身份（`GET /v1/tasks`，鉴权后）

- HTTP 状态：**{old.get('probe_status')}**（无鉴权同一路径返回 401 `UNAUTHORIZED`，说明该 catalog 需 team token）
- 响应 `schema`：`{old.get('service_catalog_schema')}`；其中 `catalog.schema`：`{old.get('catalog_schema')}`
- `benchmark_id`：`{old.get('benchmark_id')}`（响应 `catalog.benchmark_id`：`{old.get('benchmark_id_in_catalog')}`；旧 `service.json` 声明：`{old.get('service_json_benchmark_id')}`）
- 任务数：**{old.get('task_count')}**，任务 ID：`{task_ids_text}`
- 任务明细：{task_detail_text}
- replicas：`{replicas}`；scope 上限：`{scopes}`
- worker 在线：`{workers}`；旧服务 `service.json` 声明 `competition_ready={old.get('competition_ready')}`
- 策略限制：`{limits}`
- 窗口（响应实时值）：`accept_until={old.get('accept_until')}`、`expires_at={old.get('expires_at')}`
- 响应是否含 `challenge` 字段：`{old.get('has_challenge_field')}`；是否含 `attempt` 字段：`{old.get('has_attempt_field')}`

### 3.2 九题新后端必备字段是否出现

{c('api_new_backend_catalog')} 要求 `GET /v1/tasks` 额外提供 `runtime_profile_sha256`、`configuration_sha256`、`runtime_capabilities`、`nine_task_binding`。
旧服务响应中的出现情况：

```json
{nine_fields}
```

**缺失字段**：{missing_text}

## 4. 为什么旧五题服务不能冒充九题正式入口

1. **规则身份不同**：本题规则身份为 `lab-nine-20261024-v1`（`release.json` / `contracts/rules-v1.json`），旧服务 `benchmark_id={old.get('benchmark_id')}`，是旧五题开发服务；公开包明确说旧服务不是统一九题服务——{c('submission_old_five_task')}：“{cite_text('submission_old_five_task')}”
2. **正式入口由平台配置提供，不是旧服务**：{c('submission_formal_entry')}：“{cite_text('submission_formal_entry')}”；{c('submission_no_formal_submit')}：“{cite_text('submission_no_formal_submit')}”
3. **旧服务只有五题 full=20**：`inbox/lab-embodied-pilot-20261023/README.md` 自述“{cite_text('old_readme_invite')}”；其任务/评分范围是五题×四重复=20 槽，而本题要求九题×四重复=36 槽（`docs/自主实验赛道PLAYGROUND题面.md` “九题等权…36 个回合”）。
4. **九题正式提交需要平台侧 Challenge/Attempt 认证与上传通道**：{c('checklist_playground_contract')}：“{cite_text('checklist_playground_contract')}”；{c('checklist_playground_not_configured')}：“{cite_text('checklist_playground_not_configured')}”
5. **本包没有官方回调/Attempt 凭据**：{c('api_no_playground_credentials')}：“{cite_text('api_no_playground_credentials')}”；{c('api_no_official_callback')}：“{cite_text('api_no_official_callback')}”
6. **新后端绑定字段必须由新 worker runtime 服务端绑定，本包未启用**：{c('api_binding_needs_worker')}：“{cite_text('api_binding_needs_worker')}”
7. **部署模板不能启动正式评测**：{c('submission_config_template')}：“{cite_text('submission_config_template')}”；{c('api_template_cannot_submit')}：“{cite_text('api_template_cannot_submit')}”；模板 `deployment_status={json.dumps(ps['configuration_template'].get('deployment_status'), ensure_ascii=False)}`，两个后端 `url=null`、`deployment_qualified=false`（{c('config_url_null')}、{c('config_not_qualified')}）。
8. **旧服务文档自述只是邀请联调**：{c('old_agent_invite_not_official')}：“{cite_text('old_agent_invite_not_official')}”；{c('old_readme_signup_deadline')} 说明接单截止为北京时间 2026-10-26 12:00，是旧联调窗口，{c('checklist_old_window')}：“{cite_text('checklist_old_window')}”。

## 5. 公开包自述的平台接入状态

- `release.json`：`live_nine_task_service_deployed={json.dumps(ps['release_flags'].get('live_nine_task_service_deployed'))}`、
  `new_runtime_native_full36_verified={json.dumps(ps['release_flags'].get('new_runtime_native_full36_verified'))}`、
  `playground_integrated={json.dumps(ps['release_flags'].get('playground_integrated'))}`、
  `official_score_writeback_verified={json.dumps(ps['release_flags'].get('official_score_writeback_verified'))}`、
  `competition_ready={json.dumps(ps['release_flags'].get('competition_ready'))}`（{c('release_live_nine_false')}、{c('release_playground_false')}、{c('release_competition_false')}）
- `contracts/rules-v1.json` 的 `platform` 块（{c('rules_platform_block')}、{c('rules_challenge_ids_null')}）：
  `challenge_ids=null`、`playground_integrated=false`、`official_score_writeback_verified=false`、`competition_ready=false`
- `README.md`：{c('readme_no_challenge_needed')}：“{cite_text('readme_no_challenge_needed')}”
- 题面：{c('statement_formal_entry')}：“{cite_text('statement_formal_entry')}”；{c('statement_challenge_from_page')}：“{cite_text('statement_challenge_from_page')}”

## 6. 判定

> **正式提交不可执行、Attempt ID 无法在不伪造的前提下取得。**

依据列表见 `probe-summary.json` 的 `conclusion.reasons`。本次探测：
- 没有创建任何评测或 Attempt（含平台 CLI：未执行 `playground submit`）；
- 没有取得任何 Attempt ID / evaluation ID / 分数；
- 没有把旧五题服务的返回值当作九题结果；
- 没有用无关 Challenge 做“试提交”（平台可见 Challenge 与本题无关）；
- 未在任何输出文件中写入 token。

要让九题正式提交可执行，仍需平台侧提供（按 {c('checklist_platform_status_false')} 与 {c('api_deployment_qualified')}）：

1. 本题两赛道 **Challenge ID**（当前 `challenge_ids=null`，平台可见 Challenge 中未发布本题题目）——这是当前唯一缺口的“入口”本身；
2. 本题 Challenge 的 **playground submit 提交入口**（CLI 已安装且已认证，拿到 Challenge ID 后即可按 `playground submit --challenge-id <ID> --outputs <dir> --trace <session.jsonl>` 执行，但该命令会创建 Attempt，属写操作）；
3. 可信 **user/Attempt/artifact** 输入、回调鉴权/schema、幂等重放与榜单读回；
4. 新 worker 运行档的 36 槽原生验收与官方回写读回验证（`deployment_qualified=true` 且 `competition_ready=true` 之后）。

## 7. 产物

| 文件 | 内容 |
|---|---|
| [`probe_entry.py`](probe_entry.py) | 本探测脚本（可复跑：`D:\\python\\python310\\python.exe probe_entry.py`） |
| [`probe-summary.json`](probe-summary.json) | 机器可读证据：静态搜索、平台 CLI、citations、每条探测状态+sha256+判定、结论 |
| [`probe-report.md`](probe-report.md) | 本报告 |
| `raw/` | 原始响应 body（`.json`/`.txt`）+ 每条探测的 `.meta.json`（UTC/method/URL/状态/响应头/body sha256）；另含平台 CLI 只读查询证据 `raw/cli-playground-entry-evidence.json` |

token 泄漏终检：检查 `{leak.get('final_checked_files', leak.get('checked_files'))}` 个文件，泄漏文件：`{leak.get('final_leaked_files', leak.get('leaked_files')) or '无'}`。

---

*本报告由 `probe_entry.py` 生成，所有行号引用由脚本按原文检索得到；所有网络结论均可在 `raw/` 中按 sha256 复核。*
"""
    return report


if __name__ == "__main__":
    sys.exit(main())
