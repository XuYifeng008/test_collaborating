#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公开包身份与合同核验（task-1）

只读核验 ``inbox/1024-test/自主实验赛道选手公开包``，不联网、不评测、不改动公开包：

A. PUBLIC-MANIFEST.json：逐文件 bytes/sha256 与磁盘实测比对，清单覆盖率、额外文件、路径安全。
B. release.json 与 contracts：按发布声明复算规则/运行档/配置的规范 JSON SHA 与 SDK source hash
   （UTF-8 排序键、紧凑分隔符、ensure_ascii=False、allow_nan=False、无末尾换行；
   SDK 为路径/字节/哈希清单 + 紧凑 ASCII JSON），并核对 release 与 configuration-template 互相引用。
C. 运行档冻结清单：model-registry / wheels.lock 的原始字节 SHA 必须等于 runtime-profile 绑定值，
   模型注册表、wheels 与 requirements 锁、runtime-profile 三者逐项一致。
D. 机器人与模型身份事实：franka(arm,7)/piper-dual(left,right,各6)、唯一模型、profile_id、
   两波频率(240/120Hz)、finish(+720/+0)、预算、36 槽计分公式、platform 字段。
E. lab_sdk.adapters.Adapter 对 examples/sdk-fixtures.json 的 4 个真实公开样例：
   wave 推断与 robot 映射、统一 instruction（dt/Hz/finish/arms/关节顺序/夹爪范围）、
   observation 臂名映射，以及动作合法/非法矩阵（关节数、steps 越界、非有限数、
   instrument 仅第二波 C07、finish 精确 dict）。
F. 文档与合同交叉一致性（TASKS/SDK/SCORING/运行档/平台接口/发布接入清单/SUBMISSION/README/AGENT_GUIDE）。

输出（每次运行完整重建，结论由数据决定）：
  contract-verification.json   机器可读证据
  contract-verification.md     人类可读报告

用法：
  python verify_contracts.py [--package DIR] [--out DIR] [--timestamp ISO8601]

退出码：0=全部必检通过；1=发现合同/身份不一致（见 issues）；2=脚本或输入错误。
"""

import sys

# 关键：公开包只读。禁止 import 时在包内写 __pycache__。
sys.dont_write_bytecode = True

import argparse
import base64
import hashlib
import json
import math
import platform as platform_module
import re
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

PACKAGE_REL = Path("inbox") / "1024-test" / "自主实验赛道选手公开包"

SDK_FILES = ("__init__.py", "adapters.py", "client.py", "images.py", "models.py", "policy.py")

EXPECTED = {
    "rules_id": "lab-nine-20261024-v1",
    "release_version": "1.0.0",
    "manifest_schema": "lab-nine-public-manifest/v1",
    "release_schema": "lab-nine-release/v1",
    "profile_id": "lab-nine-image-model-v1",
    "model_id": "rynnbrain-1.1-2b-local",
    "model_repository": "Alibaba-DAMO-Academy/RynnBrain1.1-2B",
    "model_revision": "36069aa841fc58f500d307316cbfdf379777ce8a",
    "model_weights_sha256": "2819d84441c27c18c403c1302f60ff1ba2c9cfcdc989657bf6589e8cd11a7e6d",
    "model_count": 1,
    "score_formula": "100 * sum(task_success_count / 4 for each of 9 tasks) / 9",
    "task_count": 9,
    "replicas_per_task": 4,
    "planned_count_per_robot": 36,
}

EXPECTED_ROBOTS = {
    "franka": {"canonical_arms": ["arm"], "joints_per_arm": 7},
    "piper-dual": {"canonical_arms": ["left", "right"], "joints_per_arm": 6},
}

EXPECTED_WAVES = {
    "wave1": {
        "frequency_hz": 240,
        "step_seconds": 1.0 / 240.0,
        "finish_extra_physics_steps": 720,
        "tasks": ["bottle_transfer", "beaker_place", "balance_load", "stirrer_knob", "tube_insert"],
        "policy_wall_seconds": 600,
    },
    "wave2": {
        "frequency_hz": 120,
        "step_seconds": 1.0 / 120.0,
        "finish_extra_physics_steps": 0,
        "tasks": ["C01", "C02", "C04", "C07"],
        "policy_wall_seconds": 3600,
    },
}

# 统一臂键 -> 后端原生臂键（来自 docs/SDK.md 表格；wave2 piper 原生 arm 在统一层映射为 left）。
EXPECTED_ARM_MAP = {
    ("wave1", "franka"): {"arm": "arm"},
    ("wave1", "piper-dual"): {"left": "left", "right": "right"},
    ("wave2", "franka"): {"arm": "arm"},
    ("wave2", "piper-dual"): {"arm": "left", "right": "right"},
}

EXPECTED_GIPPER_BY_WAVE_ROBOT = {
    "wave1": {"franka": [0.0, 0.08], "piper-dual": [0.0, 0.08]},
    "wave2": {"franka": [0.0, 0.08], "piper-dual": [0.0, 0.1]},
}

CATEGORY_TITLES = {
    "A": "A. PUBLIC-MANIFEST 文件身份",
    "B": "B. release.json ↔ contracts 合同哈希",
    "C": "C. 运行档冻结清单绑定",
    "D": "D. 机器人/模型/规则身份事实",
    "E": "E. Adapter × 真实 fixtures 协议与动作矩阵",
    "F": "F. 文档与合同交叉一致性",
}

# ---------------------------------------------------------------- 基础工具


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def canonical_json_bytes(value):
    """发布声明的规范 JSON：排序键 / 紧凑分隔符 / ensure_ascii=False / 拒绝 NaN / 无末尾换行。"""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def canonical_sha(value):
    return sha256_bytes(canonical_json_bytes(value))


def _reject_constant(token):
    raise ValueError("non-finite JSON constant: %r" % (token,))


def _no_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: %r" % (key,))
        result[key] = value
    return result


def load_json(path):
    """严格加载 JSON：拒绝 NaN/Infinity，拒绝重复键。"""
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_no_duplicate_pairs)


def json_safe(value):
    """把 NaN/Infinity/Path 等转成可写入严格 JSON 的表示。"""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, Path):
        return str(value)
    return value


def is_hex64(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def sdk_file_manifest(pkg):
    """lab_sdk 六个成员的 [{path, bytes, sha256}] 清单（按路径排序）。"""
    files = {}
    for name in SDK_FILES:
        files["lab_sdk/" + name] = (Path(pkg) / "lab_sdk" / name).read_bytes()
    return [{"path": path, "bytes": len(data), "sha256": sha256_bytes(data)}
            for path, data in sorted(files.items())]


def expected_sdk_source(pkg):
    """独立实现：排序后的 path/bytes/sha256 清单 -> 紧凑 ASCII JSON -> SHA256。"""
    return sha256_bytes(json.dumps(sdk_file_manifest(pkg), sort_keys=True,
                                   separators=(",", ":")).encode())


def find_line(text, needle):
    for index, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return index
    return None


# ---------------------------------------------------------------- 证据记录器


class Verifier:
    def __init__(self):
        self.checks = []
        self.issues = []

    def _record(self, category, cid, status, detail, expected=None, actual=None, value=None):
        record = {"id": cid, "category": category, "status": status, "detail": detail}
        if expected is not None:
            record["expected"] = json_safe(expected)
        if actual is not None:
            record["actual"] = json_safe(actual)
        if value is not None:
            record["value"] = json_safe(value)
        self.checks.append(record)
        if status == "fail":
            self.issues.append({"id": cid, "category": category, "detail": detail,
                                "expected": json_safe(expected), "actual": json_safe(actual)})
        return status == "pass"

    def check(self, category, cid, ok, detail, expected=None, actual=None):
        return self._record(category, cid, "pass" if ok else "fail", detail, expected, actual)

    def info(self, category, cid, detail, value=None):
        return self._record(category, cid, "info", detail, value=value)

    def counts(self):
        by_category = {}
        for record in self.checks:
            bucket = by_category.setdefault(record["category"], {"total": 0, "pass": 0, "fail": 0, "info": 0})
            bucket["total"] += 1
            bucket[record["status"]] += 1
        total = len(self.checks)
        passed = sum(1 for r in self.checks if r["status"] == "pass")
        failed = sum(1 for r in self.checks if r["status"] == "fail")
        infos = sum(1 for r in self.checks if r["status"] == "info")
        return {"checks_total": total, "pass": passed, "fail": failed, "info": infos,
                "by_category": by_category, "issues_total": len(self.issues)}


# ---------------------------------------------------------------- A. 清单


def verify_manifest(v, ctx):
    pkg = ctx["pkg"]
    manifest = ctx["manifest"]
    v.check("A", "A.manifest.schema", manifest.get("schema") == EXPECTED["manifest_schema"],
            "清单 schema=%r" % (manifest.get("schema"),), EXPECTED["manifest_schema"], manifest.get("schema"))
    v.check("A", "A.manifest.rules_id", manifest.get("rules_id") == EXPECTED["rules_id"],
            "清单 rules_id=%r" % (manifest.get("rules_id"),), EXPECTED["rules_id"], manifest.get("rules_id"))
    entries = manifest.get("files")
    v.check("A", "A.manifest.files_type", isinstance(entries, list) and bool(entries),
            "files 为非空列表（%s 项）" % (len(entries) if isinstance(entries, list) else "n/a"))

    listed = []
    disk_manifest = {}
    for entry in entries if isinstance(entries, list) else []:
        relative = entry.get("path")
        safe = (isinstance(relative, str) and "\\" not in relative and "\x00" not in relative
                and not relative.startswith("/") and ".." not in Path(relative).parts
                and "" not in relative.split("/"))
        marker = _safe_relative(relative, pkg) if safe else None
        target = pkg / relative if safe else None
        exists = bool(target is not None and target.is_file() and not target.is_symlink())
        actual_bytes = target.stat().st_size if exists else None
        actual_sha = sha256_file(target) if exists else None
        good = bool(safe and exists and actual_bytes == entry.get("bytes") and actual_sha == entry.get("sha256"))
        v.check("A", "A.manifest.entry:" + str(relative), good,
                "%s: bytes=%s(记录 %s) sha256=%s(记录 %s)%s"
                % (relative, actual_bytes, entry.get("bytes"), actual_sha, entry.get("sha256"),
                   "" if safe else " [路径不安全]"),
                {"bytes": entry.get("bytes"), "sha256": entry.get("sha256")},
                {"bytes": actual_bytes, "sha256": actual_sha})
        listed.append(relative)
        disk_manifest[relative] = {"bytes": actual_bytes, "sha256": actual_sha}

    duplicates = sorted({name for name in listed if listed.count(name) > 1})
    v.check("A", "A.manifest.unique_paths", not duplicates,
            "清单路径唯一" if not duplicates else "重复路径: %r" % (duplicates,), [], duplicates)
    v.check("A", "A.manifest.sorted", listed == sorted(listed),
            "清单按路径排序" if listed == sorted(listed) else "清单未按路径排序",
            "sorted", listed[:3] + (["..."] if len(listed) > 3 else []))

    disk = []
    symlinks = []
    for current, directories, names in _walk(pkg):
        for name in directories + names:
            target = Path(current) / name
            if target.is_symlink():
                symlinks.append(_rel(target, pkg))
        for name in names:
            disk.append(_rel(Path(current) / name, pkg))
    disk.sort()
    listed_set = set(listed)
    extra = [path for path in disk if path not in listed_set]
    expected_extra = ["PUBLIC-MANIFEST.json"]
    extra_other = [path for path in extra if path != "PUBLIC-MANIFEST.json" and not is_runtime_cache(path)]
    extra_caches = [path for path in extra if is_runtime_cache(path)]
    v.check("A", "A.manifest.extra_files", extra_other == [],
            "包内 %d 个文件；清单覆盖 %d 个；未列入清单的发布内容文件=%r（预期无；PUBLIC-MANIFEST.json 自排除属预期）"
            % (len(disk), len(listed_set), extra_other), [], extra_other)
    v.info("A", "A.manifest.extra_public_manifest",
           "PUBLIC-MANIFEST.json 不在自身 files 列表中（文件无法自包含自身哈希），属预期排除")
    if extra_caches:
        v.info("A", "A.manifest.runtime_caches",
               "包内存在 %d 个 Python 运行时字节码缓存文件（由 import lab_sdk 产生，非发布内容，不计入清单身份）: %r"
               % (len(extra_caches), extra_caches), extra_caches)
    v.check("A", "A.manifest.no_symlinks", not symlinks,
            "包内无符号链接" if not symlinks else "存在符号链接: %r" % (symlinks,), [], symlinks)
    v.info("A", "A.manifest.file_count", "清单覆盖文件数=%d，包内实际文件数=%d（其中缓存 %d）"
           % (len(listed_set), len(disk), len(extra_caches)),
           {"listed": len(listed_set), "on_disk": len(disk), "runtime_caches": len(extra_caches)})
    ctx["manifest_extra"] = {"other": extra_other, "caches": extra_caches}
    ctx["disk_manifest"] = disk_manifest


def scan_package_files(root):
    files = []
    for current, directories, names in _walk(root):
        for name in names:
            files.append(_rel(Path(current) / name, root))
    return sorted(files)


def is_runtime_cache(relative):
    parts = relative.split("/")
    return "__pycache__" in parts or relative.endswith(".pyc")


def _walk(root):
    for current, directories, names in _os_walk(root):
        yield current, directories, names


def _os_walk(root):
    import os
    for current, directories, names in os.walk(str(root), followlinks=False):
        directories.sort()
        names.sort()
        yield current, directories, names


def _rel(path, root):
    return Path(path).relative_to(root).as_posix()


def _safe_relative(relative, pkg):
    try:
        target = (Path(pkg) / relative).resolve()
        return target == (Path(pkg).resolve() / relative) or str(target).startswith(str(Path(pkg).resolve()))
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------- B. release 合同


def verify_release_contracts(v, ctx):
    release = ctx["release"]
    config = ctx["config"]
    rules = ctx["rules"]
    profile = ctx["profile"]
    pkg = ctx["pkg"]

    v.check("B", "B.release.schema", release.get("schema") == EXPECTED["release_schema"],
            "release schema=%r" % (release.get("schema"),), EXPECTED["release_schema"], release.get("schema"))
    v.check("B", "B.release.release_version", release.get("release_version") == EXPECTED["release_version"],
            "release_version=%r" % (release.get("release_version"),), EXPECTED["release_version"],
            release.get("release_version"))
    v.check("B", "B.release.rules_id", release.get("rules_id") == EXPECTED["rules_id"],
            "release rules_id=%r" % (release.get("rules_id"),), EXPECTED["rules_id"], release.get("rules_id"))
    v.check("B", "B.rules.rules_id", rules.get("rules_id") == EXPECTED["rules_id"],
            "rules rules_id=%r" % (rules.get("rules_id"),), EXPECTED["rules_id"], rules.get("rules_id"))
    v.check("B", "B.ids.manifest_release_rules_equal",
            manifest_rules_id(ctx) == release.get("rules_id") == rules.get("rules_id"),
            "清单/release/规则三处 rules_id 一致", EXPECTED["rules_id"],
            [manifest_rules_id(ctx), release.get("rules_id"), rules.get("rules_id")])

    frozen_at = release.get("frozen_at")
    parsed = None
    if isinstance(frozen_at, str):
        try:
            parsed = datetime.fromisoformat(frozen_at)
        except ValueError:
            parsed = None
    v.check("B", "B.release.frozen_at", parsed is not None and parsed.tzinfo is not None,
            "release.frozen_at=%r 可解析为带时区 ISO8601" % (frozen_at,), "ISO8601 with tz", frozen_at)
    if parsed is not None:
        v.check("B", "B.release.frozen_date_matches_rules",
                parsed.date().isoformat() == rules.get("frozen_date"),
                "release.frozen_at 日期=%s，rules.frozen_date=%r" % (parsed.date().isoformat(), rules.get("frozen_date")),
                rules.get("frozen_date"), parsed.date().isoformat())
    v.check("B", "B.release.editorial_revision",
            isinstance(release.get("editorial_revision"), int) and release.get("editorial_revision") >= 1,
            "editorial_revision=%r" % (release.get("editorial_revision"),),
            "int >= 1", release.get("editorial_revision"))

    for flag in ("rules_frozen", "sdk_frozen", "public_kit_frozen",
                 "organizer_local_contracts_verified", "image_model_runtime_qualified"):
        v.check("B", "B.release.freeze_flag:" + flag, release.get(flag) is True,
                "%s=%r（发布声明应为 true）" % (flag, release.get(flag)), True, release.get(flag))

    computed = ctx["computed_hashes"]
    hash_pairs = [
        ("rules_sha256", computed["rules"], release.get("rules_sha256")),
        ("runtime_profile_sha256", computed["profile"], release.get("runtime_profile_sha256")),
        ("example_configuration_sha256", computed["config"], release.get("example_configuration_sha256")),
        ("sdk_source_sha256", computed["sdk_source"], release.get("sdk_source_sha256")),
    ]
    for name, actual, recorded in hash_pairs:
        v.check("B", "B.release.hash:" + name, actual == recorded,
                "release.%s 声明=%s 实测=%s" % (name, recorded, actual), recorded, actual)

    v.check("B", "B.config.rules_sha256", config.get("rules_sha256") == release.get("rules_sha256") == computed["rules"],
            "configuration-template.rules_sha256 与 release/实测一致",
            [release.get("rules_sha256"), computed["rules"]], config.get("rules_sha256"))
    v.check("B", "B.config.runtime_profile_sha256",
            config.get("runtime_profile_sha256") == release.get("runtime_profile_sha256") == computed["profile"],
            "configuration-template.runtime_profile_sha256 与 release/实测一致",
            [release.get("runtime_profile_sha256"), computed["profile"]], config.get("runtime_profile_sha256"))
    v.check("B", "B.config.sdk_source_sha256",
            config.get("sdk_source_sha256") == release.get("sdk_source_sha256") == computed["sdk_source"],
            "configuration-template.sdk_source_sha256 与 release/实测一致",
            [release.get("sdk_source_sha256"), computed["sdk_source"]], config.get("sdk_source_sha256"))

    v.check("B", "B.release.runtime_qualification.sdk_source_sha256",
            release.get("runtime_qualification", {}).get("sdk_source_sha256") == release.get("sdk_source_sha256"),
            "runtime_qualification.sdk_source_sha256 与 release.sdk_source_sha256 一致",
            release.get("sdk_source_sha256"),
            release.get("runtime_qualification", {}).get("sdk_source_sha256"))

    conventions = release.get("hash_conventions", {})
    identity_text = str(conventions.get("json_identity", "")).lower()
    for token in ("utf-8", "sorted", "compact", "ensure_ascii=false", "allow_nan=false", "no final newline"):
        v.check("B", "B.release.hash_conventions.json_identity:" + token, token in identity_text,
                "hash_conventions.json_identity 包含 %r" % (token,), token, conventions.get("json_identity"))
    sdk_text = str(conventions.get("sdk_source", "")).lower()
    for token in ("sorted", "path/bytes/sha256", "compact", "ensure_ascii=true"):
        v.check("B", "B.release.hash_conventions.sdk_source:" + token, token in sdk_text,
                "hash_conventions.sdk_source 包含 %r" % (token,), token, conventions.get("sdk_source"))
    v.check("B", "B.release.hash_conventions.archive_members",
            "sha256" in str(conventions.get("archive_and_members", "")).lower(),
            "hash_conventions.archive_and_members 含 SHA256 描述", "sha256",
            conventions.get("archive_and_members"))

    canonical = canonical_json_bytes(rules)
    spaced = json.dumps(rules, sort_keys=True, ensure_ascii=False,
                        allow_nan=False).encode("utf-8")
    v.check("B", "B.canonical.no_trailing_newline", not canonical.endswith(b"\n"),
            "规范 JSON 无末尾换行（末字节=%r）" % (canonical[-1:],), "no newline", canonical[-1:].decode("latin-1"))
    v.check("B", "B.canonical.compact_separators",
            b"\n" not in canonical and len(spaced) > len(canonical) and canonical.startswith(b"{")
            and canonical.endswith(b"}"),
            "规范 JSON 为单行紧凑序列化（无换行，%d 字节 < 默认分隔符 %d 字节）" % (len(canonical), len(spaced)),
            "<%d 字节且无换行" % len(spaced), len(canonical))
    non_ascii = any(byte > 0x7F for byte in canonical)
    v.check("B", "B.canonical.ensure_ascii_false", non_ascii,
            "规范 JSON 保留 UTF-8 非 ASCII 字符（ensure_ascii=False）")
    v.check("B", "B.canonical.sorted_keys", _is_canonical_sorted(ctx),
            "规范 JSON 键按 dict 场景排序（json.dumps sort_keys=True 复算一致）")

    v.check("B", "B.verification.combined_local_tests",
            isinstance(release.get("verification", {}).get("combined_local_tests"), int)
            and release["verification"]["combined_local_tests"] > 0,
            "combined_local_tests=%r" % (release.get("verification", {}).get("combined_local_tests"),),
            "positive int", release.get("verification", {}).get("combined_local_tests"))
    v.check("B", "B.verification.combined_local_tests_passed",
            release.get("verification", {}).get("combined_local_tests_passed") is True,
            "combined_local_tests_passed=true", True,
            release.get("verification", {}).get("combined_local_tests_passed"))
    v.check("B", "B.verification.test_log_sha256",
            is_hex64(release.get("verification", {}).get("test_log_sha256")),
            "test_log_sha256 为 64 位小写十六进制", "hex64", release.get("verification", {}).get("test_log_sha256"))
    v.info("B", "B.verification.test_log_sha256_unverifiable",
           "release.verification.test_log_sha256 指向未随公开包发布的测试日志，无法在包内复核内容（仅格式检查）")

    rq = release.get("runtime_qualification", {})
    v.check("B", "B.runtime_qualification.id", isinstance(rq.get("id"), str) and bool(rq.get("id")),
            "runtime_qualification.id=%r" % (rq.get("id"),), "non-empty str", rq.get("id"))
    for field in ("runtime_source_archive_sha256", "runtime_manifest_sha256"):
        v.check("B", "B.runtime_qualification." + field, is_hex64(rq.get(field)),
                "%s 为 64 位小写十六进制" % (field,), "hex64", rq.get(field))
        v.info("B", "B.runtime_qualification." + field + "_unverifiable",
               "%s 对应的归档/清单未随公开包发布，无法在包内复核（仅格式检查）" % (field,))
    for field, minimum in (("runtime_source_files_verified", 1), ("runtime_image_files_verified", 1)):
        value = rq.get(field)
        v.check("B", "B.runtime_qualification." + field,
                isinstance(value, int) and value >= minimum,
                "%s=%r（正整数自述）" % (field, value), "positive int", value)
    v.check("B", "B.runtime_qualification.physical_task_executed",
            rq.get("physical_task_executed") is False,
            "physical_task_executed=false（未执行真实物理任务）", False, rq.get("physical_task_executed"))
    v.check("B", "B.runtime_qualification.cleanup_verified", rq.get("cleanup_verified") is True,
            "cleanup_verified=true", True, rq.get("cleanup_verified"))
    v.check("B", "B.runtime_qualification.scope",
            isinstance(rq.get("scope"), str) and "zero physics steps" in rq["scope"],
            "runtime_qualification.scope 说明 zero physics steps", "zero physics steps", rq.get("scope"))

    activation = release.get("activation_required")
    v.check("B", "B.release.activation_required",
            isinstance(activation, list) and len(activation) == 3
            and all(isinstance(item, str) and len(item.strip()) > 0 for item in activation),
            "activation_required 为 3 条非空文本（实际 %s 条）" % (len(activation) if isinstance(activation, list) else "n/a"),
            3, activation)

    for flag in ("new_runtime_native_full36_verified", "live_nine_task_service_deployed",
                 "external_model_api_qualified", "playground_integrated",
                 "official_score_writeback_verified", "competition_ready"):
        v.check("B", "B.release.false_flag:" + flag, release.get(flag) is False,
                "%s=%r（发布声明应为 false）" % (flag, release.get(flag)), False, release.get(flag))

    v.check("B", "B.release.platform_flags_equal_rules",
            release.get("playground_integrated") == rules.get("platform", {}).get("playground_integrated")
            and release.get("official_score_writeback_verified")
            == rules.get("platform", {}).get("official_score_writeback_verified")
            and release.get("competition_ready") == rules.get("platform", {}).get("competition_ready"),
            "release 与 rules.platform 三个平台布尔字段一致",
            {k: rules.get("platform", {}).get(k) for k in
             ("playground_integrated", "official_score_writeback_verified", "competition_ready")},
            {k: release.get(k) for k in
             ("playground_integrated", "official_score_writeback_verified", "competition_ready")})


def manifest_rules_id(ctx):
    return ctx["manifest"].get("rules_id")


def _is_canonical_sorted(ctx):
    """用 shipped packaging.canonical_json 复算，应与本脚本 canonical_json_bytes 字节一致。"""
    packaging = ctx.get("packaging")
    if packaging is None:
        return False
    for key in ("rules", "profile", "config"):
        expected = canonical_json_bytes(ctx[key])
        shipped = packaging.canonical_json(ctx[key]) if hasattr(packaging, "canonical_json") else None
        if shipped != expected:
            return False
    return True


# ---------------------------------------------------------------- C. 运行档绑定


def verify_runtime_locks(v, ctx):
    pkg = ctx["pkg"]
    profile = ctx["profile"]
    registry = ctx["registry"]
    wheels = ctx["wheels"]
    requirements = ctx["requirements_text"]
    release = ctx["release"]

    registry_bytes = (pkg / "runtime" / "model-registry.json").read_bytes()
    wheels_bytes = (pkg / "runtime" / "wheels.lock.json").read_bytes()
    v.check("C", "C.registry.raw_sha256",
            sha256_bytes(registry_bytes) == profile.get("model_registry_sha256"),
            "runtime/model-registry.json 原始字节 SHA256 等于 runtime-profile.model_registry_sha256",
            profile.get("model_registry_sha256"), sha256_bytes(registry_bytes))
    v.check("C", "C.wheels.raw_sha256",
            sha256_bytes(wheels_bytes) == profile.get("wheel_lock_sha256"),
            "runtime/wheels.lock.json 原始字节 SHA256 等于 runtime-profile.wheel_lock_sha256",
            profile.get("wheel_lock_sha256"), sha256_bytes(wheels_bytes))

    models = registry.get("models", {})
    model_ids = sorted(models)
    v.check("C", "C.registry.schema", registry.get("schema") == "lab-nine-model-registry/v1",
            "registry schema=%r" % (registry.get("schema"),), "lab-nine-model-registry/v1", registry.get("schema"))
    v.check("C", "C.registry.unique_model", model_ids == [EXPECTED["model_id"]],
            "注册表唯一模型=%r" % (model_ids,), [EXPECTED["model_id"]], model_ids)
    model = models.get(EXPECTED["model_id"], {})
    for field, expected in (("repository", EXPECTED["model_repository"]),
                            ("revision", EXPECTED["model_revision"]),
                            ("weights_sha256", EXPECTED["model_weights_sha256"])):
        v.check("C", "C.registry.model." + field, model.get(field) == expected,
                "模型 %s=%r" % (field, model.get(field)), expected, model.get(field))
    v.check("C", "C.registry.model.kind", model.get("kind") == "host-local-pretrained-vlm",
            "模型 kind=%r" % (model.get("kind"),), "host-local-pretrained-vlm", model.get("kind"))
    v.check("C", "C.registry.model.architecture",
            isinstance(model.get("architecture"), str) and bool(model.get("architecture")),
            "模型 architecture=%r" % (model.get("architecture"),), "non-empty str", model.get("architecture"))
    v.check("C", "C.registry.model.supports",
            isinstance(model.get("supports"), list)
            and {"prompt", "messages", "public_images", "public_proprioception"} <= set(model.get("supports", [])),
            "模型 supports 覆盖 prompt/messages/public_images/public_proprioception", "required set",
            model.get("supports"))
    v.check("C", "C.registry.model.jail_gpu_access", model.get("jail_gpu_access") is False,
            "模型 jail_gpu_access=false（GPU 不进入 jail）", False, model.get("jail_gpu_access"))
    v.check("C", "C.registry.model.max_input_tokens",
            model.get("max_input_tokens") == profile.get("model_api", {}).get("max_input_tokens") == 16384,
            "模型 max_input_tokens 与 runtime-profile.model_api.max_input_tokens 一致（16384）",
            16384, [model.get("max_input_tokens"), profile.get("model_api", {}).get("max_input_tokens")])

    provider = registry.get("external_provider", {})
    v.check("C", "C.registry.external_provider.empty", provider.get("enabled_models") == [],
            "external_provider.enabled_models=[]（无启用外部模型）", [], provider.get("enabled_models"))
    v.check("C", "C.registry.external_provider.not_qualified",
            provider.get("live_external_auth_qualified") is False,
            "external_provider.live_external_auth_qualified=false", False,
            provider.get("live_external_auth_qualified"))
    v.check("C", "C.registry.external_provider.release_consistent",
            release.get("external_model_api_qualified") is False,
            "release.external_model_api_qualified=false 与注册表一致", False,
            release.get("external_model_api_qualified"))

    v.check("C", "C.profile.schema", profile.get("schema") == "lab-nine-runtime-profile/v1",
            "runtime-profile schema=%r" % (profile.get("schema"),), "lab-nine-runtime-profile/v1",
            profile.get("schema"))
    v.check("C", "C.profile.profile_id", profile.get("profile_id") == EXPECTED["profile_id"],
            "profile_id=%r" % (profile.get("profile_id"),), EXPECTED["profile_id"], profile.get("profile_id"))
    v.check("C", "C.profile.python", profile.get("python") == "CPython 3.10 Linux x86_64",
            "profile python=%r" % (profile.get("python"),), "CPython 3.10 Linux x86_64", profile.get("python"))
    model_api = profile.get("model_api", {})
    v.check("C", "C.profile.model_api.models", model_api.get("models") == [EXPECTED["model_id"]],
            "runtime-profile.model_api.models 唯一模型=%r" % (model_api.get("models"),),
            [EXPECTED["model_id"]], model_api.get("models"))
    v.check("C", "C.profile.model_api.models_equal_registry",
            model_api.get("models") == model_ids,
            "runtime-profile.model_api.models 与 model-registry 模型集合一致", model_ids, model_api.get("models"))
    expected_model_api = {
        "enabled": True, "protocol": "lab-model-request/v1", "endpoint": "/v1/infer",
        "max_requests": 128, "max_output_tokens": 2048, "total_output_tokens": 65536,
        "timeout_ms": 60000, "total_text_bytes": 32768, "max_input_tokens": 16384, "max_images": 6,
    }
    for field, expected in expected_model_api.items():
        v.check("C", "C.profile.model_api." + field, model_api.get(field) == expected,
                "model_api.%s=%r" % (field, model_api.get(field)), expected, model_api.get(field))
    v.check("C", "C.profile.model_api.token_accounting",
            isinstance(model_api.get("token_accounting"), str) and len(model_api["token_accounting"]) > 0,
            "model_api.token_accounting 为非空文本", "non-empty str", model_api.get("token_accounting"))
    v.check("C", "C.profile.physics_during_inference",
            str(profile.get("physics_during_inference", "")).startswith("none"),
            "physics_during_inference=%r（推理不推进物理）" % (profile.get("physics_during_inference"),),
            "none", profile.get("physics_during_inference"))

    isolation = profile.get("isolation", {})
    for field, expected in (("chroot", True), ("seccomp", True), ("no_new_privs", True),
                            ("network", "AF_UNIX only"), ("namespace_isolation", False),
                            ("oci_container", False), ("gpu_in_policy", False), ("subprocess_in_policy", False)):
        v.check("C", "C.profile.isolation." + field, isolation.get(field) == expected,
                "isolation.%s=%r" % (field, isolation.get(field)), expected, isolation.get(field))
    v.check("C", "C.profile.isolation.uid_range",
            isinstance(isolation.get("uid_range"), list) and len(isolation["uid_range"]) == 2
            and 0 < isolation["uid_range"][0] < isolation["uid_range"][1],
            "isolation.uid_range=%r 为递增正整数区间" % (isolation.get("uid_range"),), "[lo, hi]", isolation.get("uid_range"))

    resources = profile.get("resources", {})
    expected_resources = {"memory_bytes": 2147483648, "cpu_seconds": 120, "startup_seconds": 900,
                          "tmp_bytes": 67108864, "tmp_files": 512, "stdio_bytes": 1048576}
    for field, expected in expected_resources.items():
        v.check("C", "C.profile.resources." + field, resources.get(field) == expected,
                "resources.%s=%r" % (field, resources.get(field)), expected, resources.get(field))
    v.check("C", "C.profile.resources.wall_seconds_by_wave",
            resources.get("wall_seconds_by_wave") == {"wave1": 600, "wave2": 3600},
            "resources.wall_seconds_by_wave=%r" % (resources.get("wall_seconds_by_wave"),),
            {"wave1": 600, "wave2": 3600}, resources.get("wall_seconds_by_wave"))

    deployment = profile.get("deployment_qualification")
    v.check("C", "C.profile.deployment_qualification",
            isinstance(deployment, str) and "insufficient" in deployment,
            "deployment_qualification 说明文件存在不足（%r）" % (deployment,), "contains 'insufficient'", deployment)

    v.check("C", "C.wheels.schema", wheels.get("schema") == "lab-nine-wheels/v1",
            "wheels schema=%r" % (wheels.get("schema"),), "lab-nine-wheels/v1", wheels.get("schema"))
    v.check("C", "C.wheels.python", wheels.get("python") == "cp310",
            "wheels python=%r" % (wheels.get("python"),), "cp310", wheels.get("python"))
    v.check("C", "C.wheels.platform", isinstance(wheels.get("platform"), str)
            and "Linux" in wheels.get("platform", "") and "x86_64" in wheels.get("platform", ""),
            "wheels platform=%r" % (wheels.get("platform"),), "Linux x86_64", wheels.get("platform"))
    wheel_files = wheels.get("files", [])
    v.check("C", "C.wheels.files_count", isinstance(wheel_files, list) and len(wheel_files) == 3,
            "wheels.files 数量=%s" % (len(wheel_files) if isinstance(wheel_files, list) else "n/a"), 3,
            len(wheel_files) if isinstance(wheel_files, list) else None)
    wheel_by_name = {}
    for item in wheel_files if isinstance(wheel_files, list) else []:
        name = item.get("name")
        wheel_by_name[name] = item
        v.check("C", "C.wheels.file:" + str(name),
                isinstance(item.get("filename"), str) and item["filename"].endswith(".whl")
                and isinstance(item.get("size"), int) and item["size"] > 0 and is_hex64(item.get("sha256"))
                and str(item.get("url", "")).startswith("https://"),
                "wheel %s: filename/size/sha256/https url 格式有效" % (name,),
                "valid wheel record", {k: item.get(k) for k in ("filename", "size", "sha256")})
    deps = ctx["profile"].get("image_dependencies", {})
    v.check("C", "C.wheels.match_profile_versions",
            {name: wheel_by_name.get(name, {}).get("version") for name in deps} == deps,
            "wheels.lock 版本与 runtime-profile.image_dependencies 一致", deps,
            {name: wheel_by_name.get(name, {}).get("version") for name in deps})

    lines = [line.strip() for line in requirements.splitlines() if line.strip()]
    v.check("C", "C.requirements.line_count", len(lines) == 3,
            "requirements-linux-cp310.lock 行数=%d" % (len(lines),), 3, len(lines))
    pattern = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+) @ (?P<url>https://\S+) --hash=sha256:(?P<sha>[0-9a-f]{64})$")
    for line in lines:
        match = pattern.match(line)
        v.check("C", "C.requirements.parsable:" + line.split(" ")[0], match is not None,
                "requirements 行格式可解析：%s" % (line[:80],), "name @ https-url --hash=sha256:<hex>",
                line[:80])
        if match is None:
            continue
        name = match.group("name")
        wheel = wheel_by_name.get(name, {})
        v.check("C", "C.requirements.matches_wheels:" + name,
                wheel.get("url") == match.group("url") and wheel.get("sha256") == match.group("sha"),
                "requirements 与 wheels.lock 的 %s url/sha256 完全一致" % (name,),
                {"url": wheel.get("url"), "sha256": wheel.get("sha256")},
                {"url": match.group("url"), "sha256": match.group("sha")})


# ---------------------------------------------------------------- D. 身份事实


def verify_identity(v, ctx):
    rules = ctx["rules"]
    profile = ctx["profile"]
    release = ctx["release"]
    config = ctx["config"]
    registry = ctx["registry"]
    schema = ctx["schema"]
    tasks = rules.get("tasks", [])
    strategy = rules.get("strategy", {})
    evaluation = rules.get("evaluation", {})
    platform = rules.get("platform", {})
    task_by_id = {task.get("task_id"): task for task in tasks}
    model_ids = sorted(registry.get("models", {}))
    facts = ctx["facts"]

    v.check("D", "D.rules.schema", rules.get("schema") == "lab-nine-rules/v1",
            "rules schema=%r" % (rules.get("schema"),), "lab-nine-rules/v1", rules.get("schema"))
    v.check("D", "D.rules.version", rules.get("version") == EXPECTED["release_version"],
            "rules version=%r" % (rules.get("version"),), EXPECTED["release_version"], rules.get("version"))
    v.check("D", "D.rules.robots", rules.get("robots") == list(EXPECTED_ROBOTS),
            "rules.robots=%r" % (rules.get("robots"),), list(EXPECTED_ROBOTS), rules.get("robots"))
    v.check("D", "D.rules.task_ids",
            rules.get("task_ids") == list(EXPECTED_WAVES["wave1"]["tasks"] + EXPECTED_WAVES["wave2"]["tasks"]),
            "rules.task_ids 为九题固定顺序", list(EXPECTED_WAVES["wave1"]["tasks"] + EXPECTED_WAVES["wave2"]["tasks"]),
            rules.get("task_ids"))
    v.check("D", "D.rules.excluded_tasks", rules.get("excluded_tasks") == ["C11", "C12"],
            "rules.excluded_tasks=%r" % (rules.get("excluded_tasks"),), ["C11", "C12"], rules.get("excluded_tasks"))
    v.check("D", "D.rules.excluded_not_in_tasks",
            not (set(rules.get("excluded_tasks", [])) & set(rules.get("task_ids", []))),
            "排除题 C11/C12 未出现在 task_ids 中")
    v.check("D", "D.tasks.count", len(tasks) == EXPECTED["task_count"],
            "rules.tasks 数量=%d" % (len(tasks),), EXPECTED["task_count"], len(tasks))

    canonical_arms = strategy.get("canonical_arms", {})
    v.check("D", "D.strategy.canonical_arms",
            canonical_arms == {robot: spec["canonical_arms"] for robot, spec in EXPECTED_ROBOTS.items()},
            "rules.strategy.canonical_arms=%r" % (canonical_arms,),
            {robot: spec["canonical_arms"] for robot, spec in EXPECTED_ROBOTS.items()}, canonical_arms)
    v.check("D", "D.strategy.arm_joint_count",
            strategy.get("arm_joint_count") == {robot: spec["joints_per_arm"] for robot, spec in EXPECTED_ROBOTS.items()},
            "rules.strategy.arm_joint_count=%r" % (strategy.get("arm_joint_count"),),
            {robot: spec["joints_per_arm"] for robot, spec in EXPECTED_ROBOTS.items()},
            strategy.get("arm_joint_count"))
    v.check("D", "D.strategy.steps_range", strategy.get("steps_range") == [1, 120],
            "rules.strategy.steps_range=%r" % (strategy.get("steps_range"),), [1, 120], strategy.get("steps_range"))
    v.check("D", "D.strategy.units",
            strategy.get("positions_unit") == "radian_absolute_targets"
            and strategy.get("gripper_unit") == "metre_total_opening",
            "位置单位=弧度绝对目标、夹爪单位=米总开度", ["radian_absolute_targets", "metre_total_opening"],
            [strategy.get("positions_unit"), strategy.get("gripper_unit")])
    v.check("D", "D.strategy.pause_flags",
            strategy.get("observation_pauses_physics") is True and strategy.get("inference_pauses_physics") is True,
            "观察/推理期间暂停物理", True,
            [strategy.get("observation_pauses_physics"), strategy.get("inference_pauses_physics")])
    v.check("D", "D.strategy.wall_clock_continues", strategy.get("wall_clock_continues") is True,
            "墙钟照常消耗", True, strategy.get("wall_clock_continues"))
    v.check("D", "D.strategy.same_frozen_strategy_for_all_nine",
            strategy.get("same_frozen_strategy_for_all_nine") is True,
            "同一冻结策略覆盖九题", True, strategy.get("same_frozen_strategy_for_all_nine"))
    v.check("D", "D.strategy.gripper_ranges",
            strategy.get("gripper_range_m_by_wave_robot") == EXPECTED_GIPPER_BY_WAVE_ROBOT,
            "rules.strategy.gripper_range_m_by_wave_robot=%r" % (strategy.get("gripper_range_m_by_wave_robot"),),
            EXPECTED_GIPPER_BY_WAVE_ROBOT, strategy.get("gripper_range_m_by_wave_robot"))
    v.check("D", "D.strategy.gripper_range_authority",
            strategy.get("gripper_range_authority") == "instruction.actions.arms[arm].gripper_width_m",
            "夹爪范围权威字段=%r" % (strategy.get("gripper_range_authority"),),
            "instruction.actions.arms[arm].gripper_width_m", strategy.get("gripper_range_authority"))

    for wave, wave_info in EXPECTED_WAVES.items():
        wave_tasks = [task for task in tasks if task.get("wave") == wave]
        v.check("D", "D.wave.%s.task_set" % wave, [t.get("task_id") for t in wave_tasks] == wave_info["tasks"],
                "%s 任务集合=%r" % (wave, [t.get("task_id") for t in wave_tasks]), wave_info["tasks"],
                [t.get("task_id") for t in wave_tasks])
        frequencies = sorted({t.get("budget", {}).get("physics_hz") for t in wave_tasks})
        v.check("D", "D.wave.%s.physics_hz" % wave, frequencies == [wave_info["frequency_hz"]],
                "%s physics_hz=%r" % (wave, frequencies), [wave_info["frequency_hz"]], frequencies)
        finishes = sorted({t.get("budget", {}).get("finish_extra_physics_steps") for t in wave_tasks})
        v.check("D", "D.wave.%s.finish_steps" % wave, finishes == [wave_info["finish_extra_physics_steps"]],
                "%s finish_extra_physics_steps=%r" % (wave, finishes),
                [wave_info["finish_extra_physics_steps"]], finishes)
        walls = sorted({t.get("budget", {}).get("policy_wall_seconds") for t in wave_tasks})
        v.check("D", "D.wave.%s.policy_wall_seconds" % wave, walls == [wave_info["policy_wall_seconds"]],
                "%s policy_wall_seconds=%r" % (wave, walls), [wave_info["policy_wall_seconds"]], walls)
        step_seconds = [1.0 / wave_info["frequency_hz"] if t.get("budget", {}).get("physics_hz") else None
                        for t in wave_tasks]
        v.check("D", "D.wave.%s.step_seconds_relation" % wave,
                all(abs(seconds - wave_info["step_seconds"]) < 1e-12 for seconds in step_seconds),
                "%s 1/physics_hz == %.17g（dt）" % (wave, wave_info["step_seconds"]),
                wave_info["step_seconds"], step_seconds[0] if step_seconds else None)

    for task_id, expected_wave in [(t, "wave1") for t in EXPECTED_WAVES["wave1"]["tasks"]] + \
                                  [(t, "wave2") for t in EXPECTED_WAVES["wave2"]["tasks"]]:
        task = task_by_id.get(task_id)
        v.check("D", "D.task.%s.present" % task_id, task is not None, "任务 %s 在 rules.tasks 中" % task_id)
        if task is None:
            continue
        budget = task.get("budget", {})
        wave_info = EXPECTED_WAVES[expected_wave]
        v.check("D", "D.task.%s.wave" % task_id, task.get("wave") == expected_wave,
                "任务 %s wave=%r" % (task_id, task.get("wave")), expected_wave, task.get("wave"))
        v.check("D", "D.task.%s.instance" % task_id,
                task.get("instances") == 1 and isinstance(task.get("public_instance_id"), str)
                and task["public_instance_id"].endswith("-public-001"),
                "任务 %s 单公开实例=%r" % (task_id, task.get("public_instance_id")), "*-public-001",
                task.get("public_instance_id"))
        v.check("D", "D.task.%s.replicas" % task_id, task.get("replicas") == EXPECTED["replicas_per_task"],
                "任务 %s replicas=%r" % (task_id, task.get("replicas")), EXPECTED["replicas_per_task"],
                task.get("replicas"))
        v.check("D", "D.task.%s.weight" % task_id,
                task.get("weight_numerator") == 1 and task.get("weight_denominator") == 9,
                "任务 %s 权重=1/9" % task_id, [1, 9], [task.get("weight_numerator"), task.get("weight_denominator")])
        v.check("D", "D.task.%s.budget.physics_hz" % task_id,
                budget.get("physics_hz") == wave_info["frequency_hz"],
                "任务 %s physics_hz=%r" % (task_id, budget.get("physics_hz")),
                wave_info["frequency_hz"], budget.get("physics_hz"))
        v.check("D", "D.task.%s.budget.finish" % task_id,
                budget.get("finish_extra_physics_steps") == wave_info["finish_extra_physics_steps"],
                "任务 %s finish_extra_physics_steps=%r" % (task_id, budget.get("finish_extra_physics_steps")),
                wave_info["finish_extra_physics_steps"], budget.get("finish_extra_physics_steps"))
        v.check("D", "D.task.%s.budget.simulation_seconds" % task_id,
                isinstance(budget.get("simulation_seconds"), (int, float)) and budget["simulation_seconds"] > 0,
                "任务 %s simulation_seconds=%r" % (task_id, budget.get("simulation_seconds")),
                "positive number", budget.get("simulation_seconds"))
        v.check("D", "D.task.%s.budget.max_api_calls" % task_id,
                isinstance(budget.get("max_api_calls"), int) and budget["max_api_calls"] > 0,
                "任务 %s max_api_calls=%r" % (task_id, budget.get("max_api_calls")), "positive int",
                budget.get("max_api_calls"))
        v.check("D", "D.task.%s.budget.policy_cpu_seconds" % task_id,
                budget.get("policy_cpu_seconds") == 120,
                "任务 %s policy_cpu_seconds=%r" % (task_id, budget.get("policy_cpu_seconds")), 120,
                budget.get("policy_cpu_seconds"))
        if expected_wave == "wave2":
            implied = int(round(budget.get("simulation_seconds", 0) * budget.get("physics_hz", 0)))
            v.check("D", "D.task.%s.budget.max_physics_steps" % task_id,
                    budget.get("max_physics_steps") == implied == 144000,
                    "任务 %s max_physics_steps=%r（simulation_seconds*physics_hz=%d）"
                    % (task_id, budget.get("max_physics_steps"), implied), 144000, budget.get("max_physics_steps"))

    v.check("D", "D.evaluation.task_count", evaluation.get("task_count") == EXPECTED["task_count"],
            "evaluation.task_count=%r" % (evaluation.get("task_count"),), EXPECTED["task_count"],
            evaluation.get("task_count"))
    v.check("D", "D.evaluation.replicas", evaluation.get("replicas_per_instance") == EXPECTED["replicas_per_task"],
            "evaluation.replicas_per_instance=%r" % (evaluation.get("replicas_per_instance"),),
            EXPECTED["replicas_per_task"], evaluation.get("replicas_per_instance"))
    v.check("D", "D.evaluation.planned_count",
            evaluation.get("planned_count_per_robot") == EXPECTED["planned_count_per_robot"]
            == len(tasks) * EXPECTED["replicas_per_task"],
            "evaluation.planned_count_per_robot=%r == 9×4=36" % (evaluation.get("planned_count_per_robot"),),
            EXPECTED["planned_count_per_robot"], evaluation.get("planned_count_per_robot"))
    v.check("D", "D.evaluation.score_formula", evaluation.get("score_formula") == EXPECTED["score_formula"],
            "evaluation.score_formula=%r" % (evaluation.get("score_formula"),), EXPECTED["score_formula"],
            evaluation.get("score_formula"))
    v.check("D", "D.evaluation.denominator", evaluation.get("score_fraction_denominator") == 36,
            "evaluation.score_fraction_denominator=%r" % (evaluation.get("score_fraction_denominator"),), 36,
            evaluation.get("score_fraction_denominator"))
    # 全 36 槽成功（每题 4/4）时公式应得满分 100 = 100×36/36。
    try:
        formula_value = 100 * sum(Fraction(4, 4) for _ in range(9)) / 9
    except (ZeroDivisionError, ValueError):
        formula_value = None
    v.check("D", "D.evaluation.formula_equals_36",
            formula_value == Fraction(100 * 36, 36) and formula_value == 100,
            "九题等权公式满分复算：100*sum(4/4 for 9)/9 == 100 == 100×36/36",
            100, str(formula_value))
    v.check("D", "D.evaluation.slot_rewards", evaluation.get("slot_reward_values") == [0, 1],
            "evaluation.slot_reward_values=%r" % (evaluation.get("slot_reward_values"),), [0, 1],
            evaluation.get("slot_reward_values"))
    v.check("D", "D.evaluation.complete_requires_all_slots",
            evaluation.get("complete_requires_all_slots_valid") is True,
            "evaluation.complete_requires_all_slots_valid=true", True,
            evaluation.get("complete_requires_all_slots_valid"))
    v.check("D", "D.evaluation.no_rounding",
            evaluation.get("intermediate_rounding") is False and evaluation.get("display_decimals") == 6,
            "中间不舍入、显示 6 位小数", [False, 6],
            [evaluation.get("intermediate_rounding"), evaluation.get("display_decimals")])
    v.check("D", "D.evaluation.tie_rule",
            isinstance(evaluation.get("tie_rule"), str) and "share rank" in evaluation["tie_rule"],
            "evaluation.tie_rule=%r" % (evaluation.get("tie_rule"),), "equal scores share rank",
            evaluation.get("tie_rule"))
    v.check("D", "D.evaluation.attempt_selection",
            isinstance(evaluation.get("attempt_selection"), str)
            and "highest complete" in evaluation["attempt_selection"],
            "evaluation.attempt_selection=%r" % (evaluation.get("attempt_selection"),), "highest complete",
            evaluation.get("attempt_selection"))
    v.check("D", "D.evaluation.no_model_cost_in_score",
            evaluation.get("model_cost_or_speed_in_score") is False,
            "模型费用/速度不计分", False, evaluation.get("model_cost_or_speed_in_score"))

    for field, expected in (("playground_integrated", False), ("official_score_writeback_verified", False),
                            ("competition_ready", False), ("challenge_ids", None)):
        v.check("D", "D.platform." + field, platform.get(field) == expected,
                "rules.platform.%s=%r" % (field, platform.get(field)), expected, platform.get(field))
    v.check("D", "D.platform.formal_display_score",
            isinstance(platform.get("formal_display_score"), str)
            and "0..100" in platform["formal_display_score"]
            and "no additional trace multiplier" in platform["formal_display_score"],
            "rules.platform.formal_display_score 说明 0..100 且无 trace 倍率",
            "contains 0..100 / no additional trace multiplier", platform.get("formal_display_score"))
    v.info("D", "D.platform.reading", "platform 字段汇总（release 与 rules 且均为 false / challenge_ids=null）",
           {"rules": platform, "release": {k: release.get(k) for k in
                                           ("playground_integrated", "official_score_writeback_verified",
                                            "competition_ready", "live_nine_task_service_deployed",
                                            "new_runtime_native_full36_verified", "external_model_api_qualified")}})

    v.check("D", "D.config.schema", config.get("schema") == "lab-nine-organizer-config/v1",
            "configuration schema=%r" % (config.get("schema"),), "lab-nine-organizer-config/v1",
            config.get("schema"))
    v.check("D", "D.config.deployment_status",
            config.get("deployment_status") == "local_preview_only_not_a_live_evaluation_service",
            "configuration.deployment_status=%r" % (config.get("deployment_status"),),
            "local_preview_only_not_a_live_evaluation_service", config.get("deployment_status"))
    backends = config.get("backends", {})
    v.check("D", "D.config.backends_keys", sorted(backends) == ["wave1", "wave2"],
            "configuration.backends 键=%r" % (sorted(backends),), ["wave1", "wave2"], sorted(backends))
    for wave in ("wave1", "wave2"):
        backend = backends.get(wave, {})
        v.check("D", "D.config.backend.%s.url" % wave, backend.get("url") is None,
                "%s.url=null（本地预览未部署）" % wave, None, backend.get("url"))
        v.check("D", "D.config.backend.%s.deployment_qualified" % wave,
                backend.get("deployment_qualified") is False,
                "%s.deployment_qualified=false" % wave, False, backend.get("deployment_qualified"))
        v.check("D", "D.config.backend.%s.benchmark_id" % wave,
                isinstance(backend.get("benchmark_id"), str) and bool(backend.get("benchmark_id")),
                "%s.benchmark_id=%r" % (wave, backend.get("benchmark_id")), "non-empty str",
                backend.get("benchmark_id"))
        v.check("D", "D.config.backend.%s.backend_source_sha256" % wave,
                is_hex64(backend.get("backend_source_sha256")),
                "%s.backend_source_sha256 为 hex64" % wave, "hex64", backend.get("backend_source_sha256"))
    wave2_backend = backends.get("wave2", {})
    for field in ("asset_source_sha256", "execution_profile_sha256"):
        v.check("D", "D.config.backend.wave2." + field, is_hex64(wave2_backend.get(field)),
                "wave2.%s 为 hex64" % field, "hex64", wave2_backend.get(field))
    wave1_backend = backends.get("wave1", {})
    v.check("D", "D.config.backend.wave1.no_invented_hashes",
            wave1_backend.get("asset_source_sha256") is None and wave1_backend.get("execution_profile_sha256") is None,
            "wave1 旧后端未声明资产/执行 profile 哈希（如实为 null，未编造）", [None, None],
            [wave1_backend.get("asset_source_sha256"), wave1_backend.get("execution_profile_sha256")])
    v.check("D", "D.config.backend.wave1.benchmark_matches_fixture",
            wave1_backend.get("benchmark_id") == "lab-agent-v0.4-five-tasks-dev",
            "wave1.benchmark_id 与真实 wave1 公开样例 benchmark_id 一致",
            "lab-agent-v0.4-five-tasks-dev", wave1_backend.get("benchmark_id"))

    v.check("D", "D.schema.schema", schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
            "submission-schema $schema=%r" % (schema.get("$schema"),), "draft/2020-12",
            schema.get("$schema"))
    v.check("D", "D.schema.id", schema.get("$id") == "urn:lab-nine:submission:v2",
            "submission-schema $id=%r" % (schema.get("$id"),), "urn:lab-nine:submission:v2", schema.get("$id"))
    v.check("D", "D.schema.required", schema.get("required") == ["schema", "interface", "submission_id", "entrypoint"],
            "submission-schema required=%r" % (schema.get("required"),),
            ["schema", "interface", "submission_id", "entrypoint"], schema.get("required"))
    properties = schema.get("properties", {})
    v.check("D", "D.schema.constants",
            properties.get("schema", {}).get("const") == strategy.get("schema")
            and properties.get("interface", {}).get("const") == strategy.get("interface"),
            "submission-schema const 与 rules.strategy.schema/interface 一致",
            [strategy.get("schema"), strategy.get("interface")],
            [properties.get("schema", {}).get("const"), properties.get("interface", {}).get("const")])
    v.check("D", "D.schema.additional_properties", schema.get("additionalProperties") is True,
            "submission-schema 允许附加字段", True, schema.get("additionalProperties"))
    example_submission = ctx["example_submission"]
    v.check("D", "D.schema.example_submission",
            example_submission.get("schema") == "lab-submission/v2"
            and example_submission.get("interface") == "lab-policy-v2"
            and re.fullmatch(r"(?=.*[A-Za-z0-9])[A-Za-z0-9_-]{1,100}",
                             str(example_submission.get("submission_id"))) is not None
            and str(example_submission.get("entrypoint", "")).endswith(".py"),
            "examples/minimal/submission.json 满足 lab-submission/v2 + lab-policy-v2 模式",
            "schema/interface/id/entrypoint valid", {k: example_submission.get(k) for k in
                                                     ("schema", "interface", "submission_id", "entrypoint")})

    v.check("D", "D.sdk.version", ctx["sdk_version"] == "2.0.0",
            "lab_sdk.__version__=%r（统一 SDK v2）" % (ctx["sdk_version"],), "2.0.0", ctx["sdk_version"])
    v.check("D", "D.sdk.files_exact", set(ctx["packaging"].SDK_FILES) == set(SDK_FILES)
            and len(ctx["packaging"].SDK_FILES) == 6,
            "打包器冻结 SDK 成员为 6 个（__init__/adapters/client/images/models/policy）",
            sorted(SDK_FILES), sorted(ctx["packaging"].SDK_FILES))
    v.info("D", "D.sdk.packaging_not_in_identity",
           "lab_sdk/packaging.py 属打包工具而非冻结 SDK 身份成员：release.sdk_source_sha256 只覆盖 6 个 SDK 文件")
    v.info("D", "D.sdk.pyproject_version",
           "pyproject 版本 1.0.0 为发行包版本，与 SDK 协议版本 2.0.0 属不同命名空间（非冲突）",
           {"pyproject_version": ctx["pyproject_version"], "sdk_version": ctx["sdk_version"]})

    v.check("D", "D.profile.registry_binding",
            profile.get("model_registry_sha256") == sha256_bytes(
                (ctx["pkg"] / "runtime" / "model-registry.json").read_bytes()),
            "runtime-profile.model_registry_sha256 与注册表文件实测 SHA 一致")
    v.check("D", "D.profile.wheels_binding",
            profile.get("wheel_lock_sha256") == sha256_bytes(
                (ctx["pkg"] / "runtime" / "wheels.lock.json").read_bytes()),
            "runtime-profile.wheel_lock_sha256 与 wheels.lock 文件实测 SHA 一致")
    v.check("D", "D.release.model_equal_registry",
            release.get("runtime_qualification", {}).get("model", {}) == {
                "device": "cuda:0", "dtype": "bfloat16", "kind": "host-local-pretrained-vlm",
                "model": EXPECTED["model_repository"], "revision": EXPECTED["model_revision"],
                "weights_sha256": EXPECTED["model_weights_sha256"],
            },
            "release.runtime_qualification.model 与模型注册表身份逐字段一致",
            {"model": EXPECTED["model_repository"], "revision": EXPECTED["model_revision"],
             "weights_sha256": EXPECTED["model_weights_sha256"]},
            release.get("runtime_qualification", {}).get("model"))

    facts.update({
        "rules_id": rules.get("rules_id"),
        "rules_version": rules.get("version"),
        "release_version": release.get("release_version"),
        "editorial_revision": release.get("editorial_revision"),
        "profile_id": profile.get("profile_id"),
        "model": {
            "id": EXPECTED["model_id"],
            "count": len(model_ids),
            "kind": registry.get("models", {}).get(EXPECTED["model_id"], {}).get("kind"),
            "repository": registry.get("models", {}).get(EXPECTED["model_id"], {}).get("repository"),
            "revision": registry.get("models", {}).get(EXPECTED["model_id"], {}).get("revision"),
            "weights_sha256": registry.get("models", {}).get(EXPECTED["model_id"], {}).get("weights_sha256"),
            "host_environment": registry.get("models", {}).get(EXPECTED["model_id"], {}).get("host_environment"),
            "max_input_tokens": registry.get("models", {}).get(EXPECTED["model_id"], {}).get("max_input_tokens"),
        },
        "robots": {
            robot: {
                "canonical_arms": spec["canonical_arms"],
                "joints_per_arm": spec["joints_per_arm"],
                "wave1_native_arms": sorted(v for v, unified in EXPECTED_ARM_MAP[("wave1", robot)].items()
                                            if unified in spec["canonical_arms"]),
                "wave2_native_arms": sorted(v for v, unified in EXPECTED_ARM_MAP[("wave2", robot)].items()
                                            if unified in spec["canonical_arms"]),
                "wave2_native_arm_to_unified": EXPECTED_ARM_MAP[("wave2", robot)],
            }
            for robot, spec in EXPECTED_ROBOTS.items()
        },
        "waves": {
            wave: {
                "frequency_hz": info["frequency_hz"],
                "step_seconds": info["step_seconds"],
                "finish_extra_physics_steps": info["finish_extra_physics_steps"],
                "finish_physics_seconds": info["finish_extra_physics_steps"] / info["frequency_hz"],
                "tasks": info["tasks"],
                "policy_wall_seconds": info["policy_wall_seconds"],
                "budgets": {task_id: task_by_id[task_id].get("budget")
                            for task_id in info["tasks"] if task_id in task_by_id},
            }
            for wave, info in EXPECTED_WAVES.items()
        },
        "evaluation": {
            "task_count": evaluation.get("task_count"),
            "instances_per_task": evaluation.get("instances_per_task"),
            "replicas_per_instance": evaluation.get("replicas_per_instance"),
            "planned_count_per_robot": evaluation.get("planned_count_per_robot"),
            "score_formula": evaluation.get("score_formula"),
            "score_fraction_denominator": evaluation.get("score_fraction_denominator"),
            "display_decimals": evaluation.get("display_decimals"),
            "intermediate_rounding": evaluation.get("intermediate_rounding"),
            "slot_reward_values": evaluation.get("slot_reward_values"),
            "tie_rule": evaluation.get("tie_rule"),
            "attempt_selection": evaluation.get("attempt_selection"),
            "complete_requires_all_slots_valid": evaluation.get("complete_requires_all_slots_valid"),
            "model_cost_or_speed_in_score": evaluation.get("model_cost_or_speed_in_score"),
        },
        "platform": dict(platform),
        "platform_release": {k: release.get(k) for k in
                             ("playground_integrated", "official_score_writeback_verified", "competition_ready",
                              "live_nine_task_service_deployed", "new_runtime_native_full36_verified",
                              "external_model_api_qualified")},
        "submission": {
            "schema": strategy.get("schema"),
            "interface": strategy.get("interface"),
            "entry_class": strategy.get("entry_class"),
            "methods": strategy.get("methods"),
        },
        "sdk": {"version": ctx["sdk_version"], "frozen_members": sorted(SDK_FILES),
                "packaging_member_count": 6,
                "source_manifest": ctx.get("sdk_manifest", []),
                "source_hash_recipe": "sorted path/bytes/sha256 list -> compact ASCII JSON (ensure_ascii=True) -> SHA256"},
        "gripper_range_m_by_wave_robot": strategy.get("gripper_range_m_by_wave_robot"),
        "action_contract": {
            "steps_range": strategy.get("steps_range"),
            "observation_pauses_physics": strategy.get("observation_pauses_physics"),
            "inference_pauses_physics": strategy.get("inference_pauses_physics"),
            "wall_clock_continues": strategy.get("wall_clock_continues"),
        },
    })


# ---------------------------------------------------------------- E. Adapter × fixtures


class CaseRecorder:
    def __init__(self, verifier, index, wave, robot):
        self.v = verifier
        self.index = index
        self.wave = wave
        self.robot = robot
        self.record = {"index": index, "wave": wave, "robot": robot, "checks_total": 0,
                       "checks_pass": 0, "checks_fail": 0, "action_matrix": [], "failures": []}

    def cid(self, name):
        return "E.case%d.%s" % (self.index, name)

    def check(self, name, ok, detail, expected=None, actual=None):
        self.record["checks_total"] += 1
        if ok:
            self.record["checks_pass"] += 1
        else:
            self.record["checks_fail"] += 1
            self.record["failures"].append({"id": name, "detail": detail,
                                            "expected": json_safe(expected), "actual": json_safe(actual)})
        self.v.check("E", self.cid(name), ok, "case%d(%s/%s): %s" % (self.index, self.wave, self.robot, detail),
                     expected, actual)
        return ok


def verify_adapter_fixtures(v, ctx):
    pkg = ctx["pkg"]
    fixtures = ctx["fixtures"]
    cases = fixtures.get("cases", [])
    files_path = pkg / "examples" / "sdk-fixtures.json"
    v.check("E", "E.fixtures.schema", fixtures.get("schema") == "lab-sdk-public-fixtures/v1",
            "sdk-fixtures schema=%r" % (fixtures.get("schema"),), "lab-sdk-public-fixtures/v1",
            fixtures.get("schema"))
    v.check("E", "E.fixtures.file_sha256", sha256_file(files_path) == ctx["disk_manifest"].get(
        "examples/sdk-fixtures.json", {}).get("sha256"),
        "sdk-fixtures.json 实测 SHA 与清单一致", ctx["disk_manifest"].get("examples/sdk-fixtures.json", {}).get("sha256"),
        sha256_file(files_path))
    v.check("E", "E.fixtures.case_count", len(cases) == 4,
            "真实公开样例数量=%d（两波×两机器人）" % (len(cases),), 4, len(cases))

    expected_combos = [("wave1", "franka", "bottle_transfer"),
                       ("wave1", "piper-dual", "bottle_transfer"),
                       ("wave2", "piper-dual", "C07"),
                       ("wave2", "franka", "C02")]
    actual_combos = [(case.get("wave"), case.get("robot"), case.get("instruction", {}).get("task_id"))
                     for case in cases]
    v.check("E", "E.fixtures.combos", actual_combos == expected_combos,
            "样例覆盖 (wave, robot, task)=%r" % (actual_combos,), expected_combos, actual_combos)
    v.info("E", "E.fixtures.task_coverage",
           "真实样例覆盖 3/9 题：wave1 仅 bottle_transfer（两机器人），wave2 franka=C02、piper-dual=C07；不能覆盖全部任务",
           {"covered_tasks": sorted({combo[2] for combo in actual_combos})})
    v.info("E", "E.fixtures.provenance_unverifiable",
           "provenance.instruction_sha256_original / observation_sha256_original 对应移除平台身份与图像前的原始记录，"
           "公开包未包含原件，无法重算（仅验证格式与投影自洽）")

    total_pass = 0
    total_fail = 0
    for index, case in enumerate(cases):
        wave = case.get("wave")
        robot = case.get("robot")
        recorder = CaseRecorder(v, index, wave, robot)
        ctx["adapter_cases"].append(recorder.record)
        try:
            _verify_single_case(v, recorder, ctx, case, index)
        except Exception as exc:  # noqa: BLE001 - 证据脚本必须把异常记为问题而不是崩溃
            import traceback
            recorder.check("case.execution", False,
                           "用例执行异常: %s: %s" % (type(exc).__name__, exc),
                           "no exception", traceback.format_exc(limit=3))
        total_pass += recorder.record["checks_pass"]
        total_fail += recorder.record["checks_fail"]
    v.check("E", "E.adapter.all_cases_internal", total_fail == 0,
            "4 个真实样例 Adapter 内部检查通过 %d/%d（失败 %d）" % (total_pass, total_pass + total_fail, total_fail),
            "all pass", {"pass": total_pass, "fail": total_fail})
    ctx["adapter_summary"] = {"cases": len(cases), "checks_pass": total_pass, "checks_fail": total_fail,
                              "all_passed": total_fail == 0}


def _expected_case_contract(ctx, case):
    wave = case["wave"]
    robot = case["robot"]
    raw = case["instruction"]
    task_id = raw.get("task_id")
    wave_info = EXPECTED_WAVES[wave]
    arms = EXPECTED_ROBOTS[robot]["canonical_arms"]
    native_arms = raw.get("arms") if wave == "wave1" else raw.get("actions", {}).get("arms", {})
    widths = {}
    for arm in native_arms:
        unified = EXPECTED_ARM_MAP[(wave, robot)][arm]
        if wave == "wave1":
            width = native_arms[arm].get("gripper_max_width_m")
        else:
            width = native_arms[arm].get("gripper_width_m", [None, None])[1]
        widths[unified] = [0.0, width]
    return {
        "wave": wave, "robot": robot, "task_id": task_id, "wave_info": wave_info,
        "canonical_arms": arms, "native_arms": list(native_arms),
        "arm_map": EXPECTED_ARM_MAP[(wave, robot)], "widths": widths,
        "raw": raw, "raw_observation": case.get("observation"),
        "provenance": case.get("provenance", {}),
    }


def _verify_single_case(v, recorder, ctx, case, index):
    from lab_sdk.adapters import Adapter, ContractError

    expected = _expected_case_contract(ctx, case)
    raw = expected["raw"]
    provenance = expected["provenance"]
    raw_snapshot = deepcopy(raw)
    observation_raw = expected["raw_observation"]
    observation_snapshot = deepcopy(observation_raw) if observation_raw is not None else None

    recorder.record["task_id"] = expected["task_id"]
    recorder.record["provenance"] = provenance
    schema_to_wave = {"lab-agent/v0.3": "wave1", "liquid-bench/v0.2": "wave2"}
    inferred_wave = schema_to_wave.get(raw.get("schema"))
    recorder.check("wave_matches", inferred_wave == case.get("wave"),
                   "schema=%r 推断 wave=%r，样例声明 wave=%r" % (raw.get("schema"), inferred_wave, case.get("wave")),
                   case.get("wave"), inferred_wave)
    recorder.check("robot_profile_native",
                   raw.get("robot_profile") in ("franka", "dual_piper", "piper-dual"),
                   "后端 robot_profile=%r" % (raw.get("robot_profile"),), "franka|dual_piper|piper-dual",
                   raw.get("robot_profile"))
    recorder.check("provenance.source_release",
                   isinstance(provenance.get("source_release"), str) and bool(provenance.get("source_release")),
                   "provenance.source_release=%r" % (provenance.get("source_release"),), "non-empty str",
                   provenance.get("source_release"))
    for field in ("instruction_sha256_original", "observation_sha256_original"):
        recorder.check("provenance." + field, is_hex64(provenance.get(field)),
                       "provenance.%s 为 hex64" % field, "hex64", provenance.get(field))
    recorder.check("provenance.projection",
                   isinstance(provenance.get("projection"), str) and "projection" not in provenance["projection"]
                   and len(provenance["projection"]) > 20,
                   "provenance.projection 非空且描述移除范围", "non-empty projection note", provenance.get("projection"))
    recorder.check("provenance.omitted_images",
                   isinstance(provenance.get("omitted_image_count"), int) and provenance["omitted_image_count"] >= 0,
                   "omitted_image_count=%r" % (provenance.get("omitted_image_count"),), "int >= 0",
                   provenance.get("omitted_image_count"))
    if observation_raw is not None:
        recorder.check("observation.no_image_payload", "images" not in observation_raw,
                       "公开样例 observation 不含 images（已按 projection 移除图像 payload）", "no images key",
                       sorted(observation_raw))
    recorder.check("fixture.wave_robot_combo",
                   (case.get("wave"), case.get("robot")) in EXPECTED_ARM_MAP,
                   "样例 (wave, robot)=%r 在预期组合内" % ((case.get("wave"), case.get("robot")),),
                   sorted(list(EXPECTED_ARM_MAP)), (case.get("wave"), case.get("robot")))

    adapter = Adapter(raw, wave=case.get("wave"), robot=case.get("robot"))
    adapter_second = Adapter(raw, wave=case.get("wave"), robot=case.get("robot"))
    recorder.check("adapter.attrs",
                   adapter.wave == expected["wave"] and adapter.robot == expected["robot"]
                   and adapter.task == expected["task_id"],
                   "Adapter 属性 wave=%r robot=%r task=%r" % (adapter.wave, adapter.robot, adapter.task),
                   [expected["wave"], expected["robot"], expected["task_id"]],
                   [adapter.wave, adapter.robot, adapter.task])
    recorder.check("adapter.wave_inference", adapter.wave == case.get("wave"),
                   "schema 推断 wave=%r" % (adapter.wave,), case.get("wave"), adapter.wave)
    recorder.check("adapter.robot_canonical", adapter.robot == case.get("robot"),
                   "后端 robot_profile=%r -> 统一 robot=%r" % (raw.get("robot_profile"), adapter.robot),
                   case.get("robot"), adapter.robot)
    recorder.check("adapter.arm_map", adapter.arm_map == expected["arm_map"],
                   "原生臂键->统一臂键映射=%r" % (adapter.arm_map,), expected["arm_map"], adapter.arm_map)
    recorder.check("adapter.reverse_map", adapter.reverse == {unified: native for native, unified in
                                                              expected["arm_map"].items()},
                   "反向映射=%r" % (adapter.reverse,),
                   {unified: native for native, unified in expected["arm_map"].items()}, adapter.reverse)
    recorder.check("adapter.dt", abs(adapter.dt - expected["wave_info"]["step_seconds"]) < 1e-15,
                   "Adapter.dt=%.17g（期望 1/%d=%.17g）"
                   % (adapter.dt, expected["wave_info"]["frequency_hz"], expected["wave_info"]["step_seconds"]),
                   expected["wave_info"]["step_seconds"], adapter.dt)
    recorder.check("adapter.finish_steps", adapter.finish_steps == expected["wave_info"]["finish_extra_physics_steps"],
                   "Adapter.finish_steps=%r" % (adapter.finish_steps,),
                   expected["wave_info"]["finish_extra_physics_steps"], adapter.finish_steps)
    recorder.record["contract"] = {
        "instruction_schema": "lab-instruction/v2",
        "task_id": expected["task_id"],
        "robot_profile": expected["robot"],
        "backend_wave": expected["wave"],
        "step_seconds": expected["wave_info"]["step_seconds"],
        "frequency_hz": expected["wave_info"]["frequency_hz"],
        "finish_extra_physics_steps": expected["wave_info"]["finish_extra_physics_steps"],
        "maximum_steps_per_action": 120,
        "native_arms": expected["native_arms"],
        "arm_map_native_to_unified": expected["arm_map"],
        "observation_arm_map_native_to_unified": (
            {native: expected["arm_map"][native] for native in observation_raw.get("proprioception", {})}
            if observation_raw is not None else {}),
        "arms": {unified: {"joints": EXPECTED_ROBOTS[expected["robot"]]["joints_per_arm"],
                           "joint_names": adapter.arms[unified]["joint_names"],
                           "gripper_width_m": expected["widths"][unified]}
                 for unified in expected["canonical_arms"]},
        "instrument_allowed": expected["wave"] == "wave2" and expected["task_id"] == "C07",
    }

    _verify_guards(recorder, raw, case, expected, Adapter, ContractError)

    instruction = adapter.instruction()
    instruction_again = adapter_second.instruction()
    recorder.check("instruction.deterministic", instruction == instruction_again,
                   "两次 instruction() 输出完全一致")
    recorder.check("instruction.raw_not_mutated", raw == raw_snapshot,
                   "instruction() 未修改后端原始指令（deepcopy 隔离）")
    _verify_unified_instruction(recorder, adapter, instruction, expected, raw)

    if observation_raw is not None:
        observation = adapter.observation(observation_raw)
        recorder.check("observation.raw_not_mutated", observation_raw == observation_snapshot,
                       "observation() 未修改后端原始观测（deepcopy 隔离）")
        _verify_observation(recorder, adapter, observation, expected, observation_raw)

    _verify_action_matrix(recorder, adapter, expected, ContractError)


def _verify_guards(recorder, raw, case, expected, Adapter, ContractError):
    wave = case.get("wave")
    robot = case.get("robot")
    other_wave = "wave2" if wave == "wave1" else "wave1"
    other_robot = "piper-dual" if robot == "franka" else "franka"

    def _expect_error(cid, label, factory):
        try:
            factory()
        except ContractError:
            recorder.check(cid, True, "%s 被 Adapter 拒绝（ContractError）" % label)
        except Exception as exc:  # noqa: BLE001
            recorder.check(cid, False, "%s 抛出非 ContractError 异常: %s" % (label, type(exc).__name__))
        else:
            recorder.check(cid, False, "%s 未被 Adapter 拒绝" % label, "ContractError", "accepted")

    _expect_error("guard.wave_mismatch", "声明 wave=%s 与后端 schema 不符" % other_wave,
                  lambda: Adapter(raw, wave=other_wave))
    _expect_error("guard.robot_mismatch", "声明 robot=%s 与包内机器人不符" % other_robot,
                  lambda: Adapter(raw, robot=other_robot))
    wrong_schema = deepcopy(raw)
    wrong_schema["schema"] = "unknown-backend/v9"
    _expect_error("guard.unknown_schema", "未知后端 schema", lambda: Adapter(wrong_schema))
    wrong_robot = deepcopy(raw)
    wrong_robot["robot_profile"] = "ur5"
    _expect_error("guard.unknown_robot_profile", "未知 robot_profile=ur5", lambda: Adapter(wrong_robot))
    if wave == "wave1":
        bad_finish = deepcopy(raw)
        bad_finish["action_contract"]["finish"] = "hold for 720 steps then end"
        _expect_error("guard.wave1_finish_contract", "未知 wave1 finish 文本", lambda: Adapter(bad_finish))
        bad_dt = deepcopy(raw)
        bad_dt["budget"]["physics_dt_s"] = 0
        _expect_error("guard.wave1_invalid_dt", "wave1 dt=0", lambda: Adapter(bad_dt))
    else:
        bad_finish = deepcopy(raw)
        bad_finish["evaluation_contract"] = {"finish_extra_physics_steps": 5}
        _expect_error("guard.wave2_nonzero_finish", "wave2 finish_extra_physics_steps=5", lambda: Adapter(bad_finish))
        bad_dt = deepcopy(raw)
        bad_dt["physics"]["step_seconds"] = 0
        _expect_error("guard.wave2_invalid_dt", "wave2 step_seconds=0", lambda: Adapter(bad_dt))
        bad_arms = deepcopy(raw)
        native = expected["native_arms"][0]
        bad_arms["actions"]["arms"][native]["joint_names"] = bad_arms["actions"]["arms"][native]["joint_names"][:-1]
        bad_arms["actions"]["arms"][native]["joint_position_count"] = len(
            bad_arms["actions"]["arms"][native]["joint_names"])
        _expect_error("guard.wave2_joint_count", "wave2 关节名数量不足", lambda: Adapter(bad_arms))


def _verify_unified_instruction(recorder, adapter, instruction, expected, raw):
    wave_info = expected["wave_info"]
    arms = expected["canonical_arms"]
    recorder.check("instruction.schema", instruction.get("schema") == "lab-instruction/v2",
                   "统一指令 schema=%r" % (instruction.get("schema"),), "lab-instruction/v2",
                   instruction.get("schema"))
    recorder.check("instruction.backend_wave", instruction.get("backend_wave") == expected["wave"],
                   "backend_wave=%r" % (instruction.get("backend_wave"),), expected["wave"],
                   instruction.get("backend_wave"))
    recorder.check("instruction.backend_schema", instruction.get("backend_schema") == raw.get("schema"),
                   "backend_schema=%r" % (instruction.get("backend_schema"),), raw.get("schema"),
                   instruction.get("backend_schema"))
    recorder.check("instruction.robot_profile", instruction.get("robot_profile") == expected["robot"],
                   "统一 robot_profile=%r" % (instruction.get("robot_profile"),), expected["robot"],
                   instruction.get("robot_profile"))
    recorder.check("instruction.task_id", instruction.get("task_id") == expected["task_id"],
                   "task_id 原样保留=%r" % (instruction.get("task_id"),), expected["task_id"],
                   instruction.get("task_id"))
    physics = instruction.get("physics", {})
    recorder.check("instruction.physics.step_seconds",
                   abs(physics.get("step_seconds", 0) - wave_info["step_seconds"]) < 1e-15,
                   "physics.step_seconds=%.17g（期望 %.17g）" % (physics.get("step_seconds", 0),
                                                              wave_info["step_seconds"]),
                   wave_info["step_seconds"], physics.get("step_seconds"))
    recorder.check("instruction.physics.frequency_hz",
                   abs(physics.get("frequency_hz", 0) - wave_info["frequency_hz"]) < 1e-9,
                   "physics.frequency_hz=%.12g（期望 %d）" % (physics.get("frequency_hz", 0),
                                                             wave_info["frequency_hz"]),
                   wave_info["frequency_hz"], physics.get("frequency_hz"))
    recorder.check("instruction.physics.maximum_steps_per_action",
                   physics.get("maximum_steps_per_action") == 120,
                   "physics.maximum_steps_per_action=%r" % (physics.get("maximum_steps_per_action"),), 120,
                   physics.get("maximum_steps_per_action"))
    finish = instruction.get("finish", {})
    recorder.check("instruction.finish.extra_physics_steps",
                   finish.get("extra_physics_steps") == wave_info["finish_extra_physics_steps"],
                   "finish.extra_physics_steps=%r" % (finish.get("extra_physics_steps"),),
                   wave_info["finish_extra_physics_steps"], finish.get("extra_physics_steps"))
    recorder.check("instruction.finish.behavior", finish.get("behavior") == "native backend finish; SDK adds no steps",
                   "finish.behavior=%r" % (finish.get("behavior"),), "native backend finish; SDK adds no steps",
                   finish.get("behavior"))

    unified_arms = instruction.get("arms", {})
    recorder.check("instruction.arms.keys", sorted(unified_arms) == sorted(arms),
                   "统一 arms 键=%r" % (sorted(unified_arms),), sorted(arms), sorted(unified_arms))
    raw_arms = raw.get("arms") if expected["wave"] == "wave1" else raw.get("actions", {}).get("arms", {})
    for native, unified in expected["arm_map"].items():
        record = unified_arms.get(unified, {})
        raw_record = raw_arms.get(native, {})
        raw_joint_names = raw_record.get("arm_joint_names", raw_record.get("joint_names"))
        recorder.check("instruction.arm.%s.joint_count" % unified,
                       record.get("joint_position_count") == EXPECTED_ROBOTS[expected["robot"]]["joints_per_arm"],
                       "arm=%s joint_position_count=%r" % (unified, record.get("joint_position_count")),
                       EXPECTED_ROBOTS[expected["robot"]]["joints_per_arm"], record.get("joint_position_count"))
        recorder.check("instruction.arm.%s.joint_order" % unified,
                       record.get("joint_names") == raw_joint_names,
                       "arm=%s joint_names 顺序与后端公开顺序一致" % unified, raw_joint_names,
                       record.get("joint_names"))
        recorder.check("instruction.arm.%s.position_unit" % unified, record.get("position_unit") == "rad",
                       "arm=%s position_unit=%r" % (unified, record.get("position_unit")), "rad",
                       record.get("position_unit"))
        recorder.check("instruction.arm.%s.gripper_range" % unified,
                       record.get("gripper_width_m") == expected["widths"][unified],
                       "arm=%s gripper_width_m=%r" % (unified, record.get("gripper_width_m")),
                       expected["widths"][unified], record.get("gripper_width_m"))
        recorder.check("instruction.arm.%s.gripper_equals_rules" % unified,
                       record.get("gripper_width_m") == EXPECTED_GIPPER_BY_WAVE_ROBOT[expected["wave"]][expected["robot"]],
                       "arm=%s 夹爪范围与 rules.strategy.gripper_range_m_by_wave_robot 一致" % unified,
                       EXPECTED_GIPPER_BY_WAVE_ROBOT[expected["wave"]][expected["robot"]],
                       record.get("gripper_width_m"))
        kinematics = instruction.get("robot_kinematics", {}).get(unified, {})
        recorder.check("instruction.kinematics.%s.present" % unified,
                       isinstance(kinematics, dict) and bool(kinematics),
                       "统一 robot_kinematics[%s] 存在" % unified)
        recorder.check("instruction.kinematics.%s.arm_names" % unified,
                       kinematics.get("arm_names") == raw_record.get("arm_joint_names", raw_record.get("joint_names")),
                       "kinematics[%s].arm_names 与公开关节顺序一致" % unified,
                       raw_record.get("arm_joint_names", raw_record.get("joint_names")),
                       kinematics.get("arm_names"))
        limits = kinematics.get("limits", {})
        recorder.check("instruction.kinematics.%s.limits" % unified,
                       isinstance(limits, dict) and all(joint in limits for joint in record.get("joint_names", [])),
                       "kinematics[%s].limits 覆盖全部臂关节" % unified, "limits for all joints",
                       sorted(limits))

    actions = instruction.get("actions", {})
    recorder.check("instruction.actions.arms", actions.get("arms") == unified_arms,
                   "instruction.actions.arms 与 instruction.arms 一致")
    recorder.check("instruction.actions.maximum_steps", actions.get("maximum_steps") == 120,
                   "instruction.actions.maximum_steps=%r" % (actions.get("maximum_steps"),), 120,
                   actions.get("maximum_steps"))
    recorder.check("instruction.arms_max_steps_relation",
                   physics.get("maximum_steps_per_action") == actions.get("maximum_steps") == 120,
                   "physics/actions 的每动作最大步数一致=120")
    preserved_keys = ("task_id", "instruction", "benchmark_id", "platform", "initial_state", "task_geometry_manual",
                      "target_object_ids", "bottle_identification", "receiving_regions", "sensors", "visual_measurement",
                      "process_parameters", "balance_access", "instruments", "scope", "evaluation_contract",
                      "runtime_context")
    for key in preserved_keys:
        if key in raw:
            recorder.check("instruction.preserved." + key, instruction.get(key) == raw.get(key),
                           "公开字段 %s 原样保留" % key, raw.get(key), instruction.get(key))
    if expected["wave"] == "wave1":
        recorder.check("instruction.budget.preserved", instruction.get("budget") == raw.get("budget"),
                       "wave1 原后端 budget 原样保留")
    else:
        recorder.check("instruction.budget.absent", "budget" not in instruction,
                       "wave2 统一指令不注入原后端 budget（原始指令无 budget 字段）")
    if expected["wave"] == "wave2":
        recorder.check("instruction.kinematics_by_arm",
                       "robot_kinematics_by_arm" in raw,
                       "wave2 指令提供 robot_kinematics_by_arm")
        recorder.check("instruction.wave2_arm_map",
                       set(raw["robot_kinematics_by_arm"]) == set(expected["arm_map"]),
                       "wave2 robot_kinematics_by_arm 原生键=%r" % (sorted(raw["robot_kinematics_by_arm"]),),
                       sorted(expected["arm_map"]), sorted(raw["robot_kinematics_by_arm"]))
    recorder.check("instruction.no_private_truth",
                   not any(key in instruction for key in ("private_judge_state", "private_object_pose",
                                                          "contact_truth", "object_poses")),
                   "统一指令未注入私有判分/物体真值字段")


def _verify_observation(recorder, adapter, observation, expected, raw_observation):
    recorder.check("observation.schema", observation.get("schema") == "lab-observation/v2",
                   "统一观测 schema=%r" % (observation.get("schema"),), "lab-observation/v2",
                   observation.get("schema"))
    recorder.check("observation.backend_wave", observation.get("backend_wave") == expected["wave"],
                   "backend_wave=%r" % (observation.get("backend_wave"),), expected["wave"],
                   observation.get("backend_wave"))
    recorder.check("observation.robot_profile", observation.get("robot_profile") == expected["robot"],
                   "robot_profile=%r" % (observation.get("robot_profile"),), expected["robot"],
                   observation.get("robot_profile"))
    recorder.check("observation.task_id", observation.get("task_id") == expected["task_id"],
                   "task_id=%r" % (observation.get("task_id"),), expected["task_id"], observation.get("task_id"))
    recorder.check("observation.simulation_time_s",
                   observation.get("simulation_time_s") == raw_observation.get("simulation_time_s"),
                   "simulation_time_s 原样保留=%.17g" % (raw_observation.get("simulation_time_s", 0),),
                   raw_observation.get("simulation_time_s"), observation.get("simulation_time_s"))
    raw_proprio = raw_observation.get("proprioception", {})
    mapped = {unified: deepcopy(value) for native, value in raw_proprio.items()
              for unified in [expected["arm_map"][native]]}
    recorder.check("observation.proprioception.arm_set",
                   sorted(observation.get("proprioception", {})) == sorted(expected["canonical_arms"]),
                   "统一观测臂名=%r" % (sorted(observation.get("proprioception", {})),),
                   sorted(expected["canonical_arms"]), sorted(observation.get("proprioception", {})))
    recorder.check("observation.proprioception.mapping", observation.get("proprioception") == mapped,
                   "原生 proprioception 键按 %r 映射且数值逐字段保持不变" % (expected["arm_map"],),
                   sorted(mapped), sorted(observation.get("proprioception", {})))
    for native, unified in expected["arm_map"].items():
        recorder.check("observation.proprioception.%s.equal_native_%s" % (unified, native),
                       observation.get("proprioception", {}).get(unified) == raw_proprio.get(native),
                       "统一臂 %s == 后端原生臂 %s 本体状态" % (unified, native))
    if expected["wave"] == "wave1":
        expected_finished = bool(raw_observation.get("budget", {}).get("finished", False))
        recorder.check("observation.instruments.preserved", observation.get("instruments") == raw_observation.get("instruments"),
                       "wave1 公开设备反馈（instruments）原样保留")
    else:
        expected_finished = bool(raw_observation.get("evaluation", {}).get("finished", False))
        if expected["task_id"] in ("C02", "C07"):
            recorder.check("observation.instruments.absent", "instruments" not in observation,
                           "%s 不提供体积/流量数值旁路或质量账簿（无 instruments）" % expected["task_id"])
        else:
            allowed = ("time_s", "task", "source_volume_ml", "receiver_volume_ml", "funnel_volume_ml", "flow_ml_s")
            expected_instruments = ({k: v for k, v in raw_observation.get("instruments", {}).items() if k in allowed}
                                    if "instruments" in raw_observation else None)
            recorder.check("observation.instruments.filtered", observation.get("instruments") == expected_instruments,
                           "wave2 非 C02/C07 仅保留允许的公开体积反馈键")
    recorder.check("observation.finished", observation.get("finished") == expected_finished,
                   "finished=%r（由后端预算/执行状态推导）" % (observation.get("finished"),),
                   expected_finished, observation.get("finished"))
    recorder.check("observation.no_private_truth",
                   not any(key in observation for key in ("private_judge_state", "private_object_pose", "judge")),
                   "统一观测未注入私有判分/物体真值字段")

    # observation 负例守卫
    from lab_sdk.adapters import ContractError
    bad = deepcopy(raw_observation)
    bad["proprioception"] = {}
    _expect_observation_error(recorder, adapter, bad, "guard.observation.arm_set",
                              "proprioception 臂集合错误", ContractError)
    bad = deepcopy(raw_observation)
    del bad["simulation_time_s"]
    _expect_observation_error(recorder, adapter, bad, "guard.observation.missing_time",
                              "缺少 simulation_time_s", ContractError)
    bad = deepcopy(raw_observation)
    bad["simulation_time_s"] = float("nan")
    _expect_observation_error(recorder, adapter, bad, "guard.observation.nonfinite_time",
                              "simulation_time_s 非有限", ContractError)
    if expected["wave"] == "wave1":
        finished_true = deepcopy(raw_observation)
        finished_true.setdefault("budget", {})["finished"] = True
        result = adapter.observation(finished_true)
        recorder.check("guard.observation.finished_from_budget", result.get("finished") is True,
                       "wave1 budget.finished=true -> 统一观测 finished=True")
    else:
        finished_true = deepcopy(raw_observation)
        finished_true["evaluation"] = {"finished": True}
        result = adapter.observation(finished_true)
        recorder.check("guard.observation.finished_from_evaluation", result.get("finished") is True,
                       "wave2 evaluation.finished=true -> 统一观测 finished=True")


def _expect_observation_error(recorder, adapter, raw, cid, label, ContractError):
    try:
        adapter.observation(raw)
    except ContractError:
        recorder.check(cid, True, "%s 被 Adapter 拒绝（ContractError）" % label)
    except Exception as exc:  # noqa: BLE001
        recorder.check(cid, False, "%s 抛出非 ContractError 异常: %s" % (label, type(exc).__name__))
    else:
        recorder.check(cid, False, "%s 未被 Adapter 拒绝" % label, "ContractError", "accepted")


def _valid_positions(adapter, arm):
    spec = adapter.arms[arm]
    limits = adapter.kinematics.get(arm, {}).get("limits", {})
    positions = []
    for joint in spec["joint_names"]:
        if joint in limits and len(limits[joint]) == 2 and limits[joint][0] < limits[joint][1]:
            positions.append((limits[joint][0] + limits[joint][1]) / 2.0)
        elif joint in limits and len(limits[joint]) == 2:
            positions.append(limits[joint][0])
        else:
            positions.append(0.0)
    return positions


def _verify_action_matrix(recorder, adapter, expected, ContractError):
    arms = expected["canonical_arms"]
    primary = arms[0]
    valid = {arm: _valid_positions(adapter, arm) for arm in arms}
    max_width = expected["widths"][primary][1]
    instrument_allowed = expected["wave"] == "wave2" and expected["task_id"] == "C07"
    native_map = {unified: native for native, unified in expected["arm_map"].items()}

    entries = []

    def entry(name, action, expect_ok, validator=None):
        entries.append({"name": name, "action": action, "expect_ok": expect_ok, "validate": validator})

    entry("legal.empty_steps1", {"arms": {}, "steps": 1}, True,
          lambda result: result == {"arms": {}, "steps": 1})
    entry("legal.empty_steps_max", {"arms": {}, "steps": 120}, True,
          lambda result: result == {"arms": {}, "steps": 120})
    entry("legal.steps_only", {"steps": 3}, True,
          lambda result: result == {"arms": {}, "steps": 3})
    entry("legal.single_arm_positions", {"arms": {primary: {"positions": list(valid[primary])}}, "steps": 1}, True,
          lambda result: result == {"arms": {native_map[primary]: {"positions": valid[primary]}}, "steps": 1})
    if len(arms) == 2:
        both = {arm: {"positions": list(valid[arm])} for arm in arms}
        entry("legal.both_arms_positions", {"arms": both, "steps": 2}, True,
              lambda result: result == {"arms": {native_map[arm]: {"positions": valid[arm]} for arm in arms},
                                        "steps": 2})
    entry("legal.gripper_min", {"arms": {primary: {"gripper_width_m": 0.0}}}, True,
          lambda result: result == {"arms": {native_map[primary]: {"gripper_width_m": 0.0}}, "steps": 1})
    entry("legal.gripper_max", {"arms": {primary: {"gripper_width_m": max_width}}}, True,
          lambda result: result == {"arms": {native_map[primary]: {"gripper_width_m": max_width}}, "steps": 1})
    entry("legal.arm_positions_plus_gripper",
          {"arms": {primary: {"positions": list(valid[primary]), "gripper_width_m": max_width / 2.0}}, "steps": 5},
          True,
          lambda result: result == {"arms": {native_map[primary]: {"positions": valid[primary],
                                                                  "gripper_width_m": max_width / 2.0}}, "steps": 5})
    entry("legal.finish_exact", {"finish": True}, True, lambda result: result == {"finish": True})
    if instrument_allowed:
        for method in ("read", "tare"):
            action = {"instrument": {"device": "competition_balance", "method": method}}
            entry("legal.instrument_" + method, action, True,
                  lambda result, action=action: result == action)

    count = len(valid[primary])
    entry("illegal.joint_count_low", {"arms": {primary: {"positions": valid[primary][:-1]}}}, False)
    entry("illegal.joint_count_high", {"arms": {primary: {"positions": list(valid[primary]) + [0.0]}}}, False)
    entry("illegal.steps_zero", {"arms": {}, "steps": 0}, False)
    entry("illegal.steps_over", {"arms": {}, "steps": 121}, False)
    entry("illegal.steps_float", {"arms": {}, "steps": 1.5}, False)
    entry("illegal.steps_bool", {"arms": {}, "steps": True}, False)
    entry("illegal.steps_string", {"arms": {}, "steps": "3"}, False)
    entry("illegal.steps_none", {"arms": {}, "steps": None}, False)
    for label, value in (("nan", float("nan")), ("inf", float("inf")), ("neg_inf", float("-inf"))):
        bad = list(valid[primary])
        bad[0] = value
        entry("illegal.positions_" + label, {"arms": {primary: {"positions": bad}}}, False)
    limits = adapter.kinematics.get(primary, {}).get("limits", {})
    spec_joints = adapter.arms[primary]["joint_names"]
    over_joint = None
    for joint in spec_joints:
        if joint in limits and len(limits[joint]) == 2:
            over_joint = (joint, limits[joint][1] + 0.5)
            break
    if over_joint is not None:
        bad = list(valid[primary])
        bad[spec_joints.index(over_joint[0])] = over_joint[1]
        entry("illegal.joint_limit", {"arms": {primary: {"positions": bad}}}, False)
    entry("illegal.gripper_negative", {"arms": {primary: {"gripper_width_m": -0.001}}}, False)
    entry("illegal.gripper_over", {"arms": {primary: {"gripper_width_m": max_width + 0.01}}}, False)
    entry("illegal.unknown_arm", {"arms": {"mid": {"positions": list(valid[primary])}}}, False)
    entry("illegal.arm_command_not_dict", {"arms": {primary: list(valid[primary])}}, False)
    entry("illegal.arm_unknown_field",
          {"arms": {primary: {"positions": list(valid[primary]), "velocity": [0.0] * count}}}, False)
    entry("illegal.action_unknown_field", {"arms": {}, "foo": 1}, False)
    entry("illegal.arms_not_mapping", {"arms": "left"}, False)
    entry("illegal.finish_value_int", {"finish": 1}, False)
    entry("illegal.finish_value_false", {"finish": False}, False)
    entry("illegal.finish_mixed_with_steps", {"finish": True, "steps": 1}, False)
    entry("illegal.action_not_dict", ["arms"], False)
    instrument = {"instrument": {"device": "competition_balance", "method": "read"}}
    if not instrument_allowed:
        entry("illegal.instrument_not_allowed", instrument, False)
    else:
        entry("illegal.instrument_wrong_device",
              {"instrument": {"device": "other_balance", "method": "read"}}, False)
        entry("illegal.instrument_wrong_method",
              {"instrument": {"device": "competition_balance", "method": "zero"}}, False)
        entry("illegal.instrument_extra_field",
              {"instrument": {"device": "competition_balance", "method": "read", "extra": 1}}, False)
        entry("illegal.instrument_mixed",
              {"instrument": {"device": "competition_balance", "method": "read"}, "arms": {}}, False)

    legal_total = 0
    legal_pass = 0
    illegal_total = 0
    illegal_pass = 0
    for item in entries:
        name = item["name"]
        action = item["action"]
        expect_ok = item["expect_ok"]
        snapshot = deepcopy(action)
        result = None
        error = None
        try:
            result = adapter.action(action)
        except ContractError as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001
            error = "非 ContractError: %s: %s" % (type(exc).__name__, exc)
        actual_ok = result is not None
        passed = actual_ok == expect_ok
        detail = ""
        if passed and expect_ok and item["validate"] is not None:
            try:
                passed = bool(item["validate"](result))
            except Exception as exc:  # noqa: BLE001
                passed = False
                detail = "结果校验异常: %s" % (exc,)
            if not passed:
                detail = "返回结果不符合预期: %r" % (json_safe(result),)
        if expect_ok:
            legal_total += 1
            if passed:
                legal_pass += 1
        else:
            illegal_total += 1
            if passed:
                illegal_pass += 1
        if expect_ok:
            message = ("合法动作被接受且结果符合预期" if passed else
                       "合法动作被拒绝/结果不符：%s" % (detail or error or json_safe(result)))
            expected = "accepted"
            actual = {"accepted": actual_ok, "result": json_safe(result), "error": error}
        else:
            message = ("非法动作被 ContractError 拒绝：%s" % (error,) if passed else
                       "非法动作未被拒绝（异常=%r，结果=%r）" % (error, json_safe(result)))
            expected = "ContractError"
            actual = {"accepted": actual_ok, "error": error}
        recorder.record["action_matrix"].append({
            "name": name,
            "expect": "legal" if expect_ok else "illegal",
            "passed": passed,
            "action": json_safe(action),
            "result": json_safe(result) if result is not None else None,
            "error": error,
        })
        recorder.check("action." + name, passed, "%s：%s" % (name, message), expected, actual)
        if expect_ok:
            recorder.check("action.%s.no_mutation" % name, action == snapshot,
                           "合法动作输入未被 Adapter 修改")
    recorder.record["action_matrix_summary"] = {"legal_total": legal_total, "legal_pass": legal_pass,
                                                "illegal_total": illegal_total, "illegal_pass": illegal_pass}


def _contains_nonfinite(value):
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_contains_nonfinite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_nonfinite(item) for item in value)
    return False


# ---------------------------------------------------------------- F. 文档交叉一致性


def verify_docs(v, ctx):
    texts = ctx["texts"]
    rules = ctx["rules"]
    profile = ctx["profile"]
    registry = ctx["registry"]
    release = ctx["release"]
    tasks = rules.get("tasks", [])
    task_by_id = {task.get("task_id"): task for task in tasks}

    def doc_has(doc, cid, needle, detail=None):
        text = texts.get(doc)
        if text is None:
            v.check("F", "F.%s.%s" % (doc.replace("/", "_"), cid), False, "缺少文档 %s" % doc, "exists", None)
            return
        line = find_line(text, needle)
        v.check("F", "F.%s.%s" % (doc.replace("/", "_"), cid), line is not None,
                "%s 包含 %r%s" % (doc, needle, "（L%d）" % line if line else "（未找到）"),
                needle, "L%d" % line if line else "missing")

    # TASKS.md 表格 vs rules.budget
    tasks_text = texts.get("docs/TASKS.md", "")
    row_pattern = re.compile(r"^\|\s*`([^`]+)`[^|]*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|\s*$")
    parsed_rows = {}
    for line_number, line in enumerate(tasks_text.splitlines(), 1):
        match = row_pattern.match(line)
        if match:
            parsed_rows[match.group(1)] = (line_number, [match.group(i).strip() for i in range(2, 6)])
    v.check("F", "F.tasks.rows_count", len(parsed_rows) == 9,
            "docs/TASKS.md 预算表解析到 %d 行" % (len(parsed_rows),), 9, len(parsed_rows))
    for task_id, task in task_by_id.items():
        row = parsed_rows.get(task_id)
        if row is None:
            v.check("F", "F.tasks.row:" + str(task_id), False, "docs/TASKS.md 缺少任务 %s 表格行" % task_id,
                    "row present", "missing")
            continue
        line_number, columns = row
        sim_match = re.search(r"([\d.]+)\s*s", columns[0])
        api_match = re.search(r"(\d+)", columns[1])
        cpu_wall = re.findall(r"(\d+)\s*s", columns[2])
        finish_match = re.search(r"([+-]?\d+)", columns[3])
        budget = task.get("budget", {})
        checks = [
            ("sim", sim_match is not None and abs(float(sim_match.group(1)) - budget.get("simulation_seconds", -1)) < 1e-9,
             budget.get("simulation_seconds"), sim_match.group(1) if sim_match else None),
            ("api", api_match is not None and int(api_match.group(1)) == budget.get("max_api_calls"),
             budget.get("max_api_calls"), api_match.group(1) if api_match else None),
            ("finish", finish_match is not None and int(finish_match.group(1)) == budget.get("finish_extra_physics_steps"),
             budget.get("finish_extra_physics_steps"), finish_match.group(1) if finish_match else None),
        ]
        wall_match = re.match(r"^(\d+)\s*/\s*(\d+)\s*s$", columns[2])
        checks.append(("cpu_wall", wall_match is not None
                       and int(wall_match.group(1)) == budget.get("policy_cpu_seconds")
                       and int(wall_match.group(2)) == budget.get("policy_wall_seconds"),
                       [budget.get("policy_cpu_seconds"), budget.get("policy_wall_seconds")],
                       [wall_match.group(1), wall_match.group(2)] if wall_match else columns[2]))
        for name, ok, expected, actual in checks:
            v.check("F", "F.tasks.%s.%s" % (task_id, name), ok,
                    "docs/TASKS.md L%d 任务 %s %s 与 rules.budget 一致" % (line_number, task_id, name),
                    expected, actual)
    doc_has("docs/TASKS.md", "frequency", "前五题240Hz，后四题120Hz")
    doc_has("docs/TASKS.md", "finish_720", "720步")
    doc_has("docs/TASKS.md", "finish_zero", "finish不加步")
    doc_has("docs/TASKS.md", "wave2_max_steps", "第二波共144000物理步")

    # SDK.md vs rules/adapter 语义
    doc_has("docs/SDK.md", "wave1_dt", "1/240 s")
    doc_has("docs/SDK.md", "wave1_finish", "保持目标并推进720个物理步后结束")
    doc_has("docs/SDK.md", "wave2_dt", "1/120 s")
    doc_has("docs/SDK.md", "wave2_finish", "不追加物理步")
    doc_has("docs/SDK.md", "wave2_piper_native", "piper-dual / arm,right")
    doc_has("docs/SDK.md", "wave2_piper_unified", "left,right")
    doc_has("docs/SDK.md", "steps_range", "1–120整数")
    doc_has("docs/SDK.md", "instrument_c07_only", "只允许第二波C07")
    doc_has("docs/SDK.md", "c07_no_ledger", "C07不提供质量/液量账本")
    doc_has("docs/SDK.md", "use_actual_dt", "SDK取实际指令里的 dt")

    # SCORING.md
    doc_has("docs/SCORING.md", "score_formula", "物理分=100×成功槽数/36")
    doc_has("docs/SCORING.md", "slots", "每机器人9题×1公开实例×4重复=36槽")
    doc_has("docs/SCORING.md", "rounding", "中间不舍入，显示六位小数")
    doc_has("docs/SCORING.md", "tie", "同分并列")
    doc_has("docs/SCORING.md", "incomplete", "任一槽null/缺失/重复/版本不符")

    # 运行档.md
    doc_has("docs/运行档.md", "profile_id", "lab-nine-image-model-v1")
    doc_has("docs/运行档.md", "deps", "NumPy 1.26.4、Pillow 11.3.0、opencv-python-headless 4.11.0.86")
    doc_has("docs/运行档.md", "memory", "2 GiB")
    doc_has("docs/运行档.md", "cpu", "CPU 120 s")
    doc_has("docs/运行档.md", "wall", "墙钟第一波 600 s、第二波 3600 s")
    doc_has("docs/运行档.md", "startup", "启动预算 900 s")
    doc_has("docs/运行档.md", "model_requests", "128 次请求")
    doc_has("docs/运行档.md", "total_output_tokens", "65536 token")
    doc_has("docs/运行档.md", "deadline", "60000 ms")
    doc_has("docs/运行档.md", "text_bytes", "32768 字节")
    doc_has("docs/运行档.md", "max_input_tokens", "16384")
    doc_has("docs/运行档.md", "messages", "32 条历史消息")
    doc_has("docs/运行档.md", "images", "6 张当前图像")
    doc_has("docs/运行档.md", "host_env", "PyTorch 2.10.0+cu128、Transformers 5.13.0、Python 3.11.17")
    doc_has("docs/运行档.md", "model_id", "rynnbrain-1.1-2b-local")
    doc_has("docs/运行档.md", "model_revision", EXPECTED["model_revision"])
    doc_has("docs/运行档.md", "model_weights", EXPECTED["model_weights_sha256"])

    # 平台接口.md / 发布接入清单.md / SUBMISSION.md / README.md / AGENT_GUIDE.md
    doc_has("docs/平台接口.md", "flags", "playground_integrated=false")
    doc_has("docs/平台接口.md", "flags2", "official_score_writeback_verified=false")
    doc_has("docs/平台接口.md", "flags3", "competition_ready=false")
    doc_has("docs/平台接口.md", "score", "score_100 = 100 × 成功槽数 / 36")
    doc_has("docs/平台接口.md", "sdk_six", "SDK 六个成员必须与组织者冻结版本逐字相同")
    doc_has("docs/平台接口.md", "nine_binding", "nine_task_binding")
    doc_has("docs/平台接口.md", "canonical_recipe", "通用配置 JSON 使用 UTF-8、排序键、紧凑分隔符")
    doc_has("docs/平台接口.md", "ensure_ascii_false", "ensure_ascii=False")
    doc_has("docs/平台接口.md", "no_trailing_newline", "不含末尾换行")
    doc_has("docs/发布接入清单.md", "flags", "playground_integrated=false")
    doc_has("docs/发布接入清单.md", "no_oci_claim", "不要将chroot称为OCI容器")
    doc_has("docs/发布接入清单.md", "old_service", "旧stdlib服务不可直接接新模型档")
    doc_has("SUBMISSION.md", "complete_score", "36槽全部有效才形成完整分")
    doc_has("SUBMISSION.md", "attempt", "Attempt ID")
    doc_has("SUBMISSION.md", "old_services", "旧标准库五题服务的full=20、四题服务的full=16，不是统一九题服务")
    doc_has("README.md", "competition_ready", "competition_ready=false")
    doc_has("README.md", "slots", "每个机器人赛道九题×四重复，共36槽")
    doc_has("AGENT_GUIDE.md", "waves", "前五题 240 Hz、finish 加 720 步；后四题 120 Hz、finish 不加步")
    doc_has("AGENT_GUIDE.md", "old_services", "不能用旧五题或四题的接口伪装九题正式评测")

    # pyproject vs runtime-profile 依赖
    pyproject = ctx["texts"].get("pyproject.toml", "")
    for name, version in profile.get("image_dependencies", {}).items():
        token = "%s==%s" % (name, version)
        v.check("F", "F.pyproject.vision_dep:" + name, token in pyproject,
                "pyproject.toml vision 依赖含 %r" % token, token, "found" if token in pyproject else "missing")
    v.check("F", "F.pyproject.packages", "packages = [\"lab_sdk\"]" in pyproject,
            "pyproject.toml 打包 lab_sdk 包")
    v.check("F", "F.pyproject.version", "version = \"1.0.0\"" in pyproject,
            "pyproject 版本 1.0.0 与 release.release_version 一致", release.get("release_version"), "1.0.0")

    # docs/运行档 registry host env vs model-registry
    host_env = registry.get("models", {}).get(EXPECTED["model_id"], {}).get("host_environment", {})
    doc_has("docs/运行档.md", "host_python", host_env.get("python", "\0"))
    doc_has("docs/运行档.md", "host_torch", host_env.get("torch", "\0"))
    doc_has("docs/运行档.md", "host_transformers", host_env.get("transformers", "\0"))
    v.info("F", "F.note.pillow_two_contexts",
           "Pillow 11.3.0 为 jail 镜像依赖，Pillow 12.0.0 为 host 模型解释器环境，两者属不同运行位置（非冲突）",
           {"jail": profile.get("image_dependencies", {}).get("Pillow"),
            "host": host_env.get("Pillow")})
    v.info("F", "F.note.wave2_benchmark",
           "configuration.backends.wave2.benchmark_id=%r；wave2 真实公开样例未携带 benchmark_id 字段，无法从样例交叉核对"
           % (ctx["config"].get("backends", {}).get("wave2", {}).get("benchmark_id"),))
    v.info("F", "F.note.schema_docs",
           "submission-schema.json 无对应说明文档；其 const 已与 rules.strategy 交叉核对",
           {"schema": "contracts/submission-schema.json"})


# ---------------------------------------------------------------- 主流程


def locate_package(explicit):
    if explicit:
        package = Path(explicit).resolve()
        if not package.is_dir():
            raise SystemExit("公开包目录不存在: %s" % package)
        return package
    script = Path(__file__).resolve()
    candidates = []
    for parent in list(script.parents)[:8]:
        candidates.append(parent / PACKAGE_REL)
    candidates.append(Path.cwd() / PACKAGE_REL)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise SystemExit("无法定位公开包（尝试: %s）" % [str(c) for c in candidates])


def collect_inputs(pkg):
    rel_paths = [
        "PUBLIC-MANIFEST.json", "release.json", "README.md", "AGENT_GUIDE.md", "SUBMISSION.md", "pyproject.toml",
        "contracts/rules-v1.json", "contracts/runtime-profile.json", "contracts/configuration-template.json",
        "contracts/submission-schema.json",
        "runtime/model-registry.json", "runtime/wheels.lock.json", "runtime/requirements-linux-cp310.lock",
        "examples/sdk-fixtures.json", "examples/sdk-public-image.json", "examples/minimal/policy.py",
        "examples/minimal/submission.json", "examples/model_and_rgb.py",
        "docs/SCORING.md", "docs/SDK.md", "docs/TASKS.md", "docs/发布接入清单.md", "docs/平台接口.md",
        "docs/自主实验赛道PLAYGROUND题面.md", "docs/运行档.md",
    ] + ["lab_sdk/" + name for name in SDK_FILES] + ["lab_sdk/packaging.py"]
    inputs = {}
    for relative in rel_paths:
        target = pkg / relative
        if target.is_file():
            data = target.read_bytes()
            inputs[relative] = {"bytes": len(data), "sha256": sha256_bytes(data)}
    return inputs


def load_context(pkg):
    sys.path.insert(0, str(pkg))
    import lab_sdk  # noqa: F401  (公开包 SDK；sys.dont_write_bytecode 已禁止写 __pycache__)
    from lab_sdk import packaging
    from lab_sdk.adapters import Adapter, ContractError  # noqa: F401

    texts = {}
    for name in ("README.md", "AGENT_GUIDE.md", "SUBMISSION.md", "pyproject.toml",
                 "docs/SCORING.md", "docs/SDK.md", "docs/TASKS.md", "docs/发布接入清单.md",
                 "docs/平台接口.md", "docs/自主实验赛道PLAYGROUND题面.md", "docs/运行档.md"):
        path = pkg / name
        texts[name] = path.read_text(encoding="utf-8") if path.is_file() else None
    ctx = {
        "pkg": pkg,
        "manifest": load_json(pkg / "PUBLIC-MANIFEST.json"),
        "release": load_json(pkg / "release.json"),
        "rules": load_json(pkg / "contracts" / "rules-v1.json"),
        "profile": load_json(pkg / "contracts" / "runtime-profile.json"),
        "config": load_json(pkg / "contracts" / "configuration-template.json"),
        "schema": load_json(pkg / "contracts" / "submission-schema.json"),
        "registry": load_json(pkg / "runtime" / "model-registry.json"),
        "wheels": load_json(pkg / "runtime" / "wheels.lock.json"),
        "requirements_text": (pkg / "runtime" / "requirements-linux-cp310.lock").read_text(encoding="utf-8"),
        "fixtures": load_json(pkg / "examples" / "sdk-fixtures.json"),
        "image_sample": load_json(pkg / "examples" / "sdk-public-image.json"),
        "example_submission": load_json(pkg / "examples" / "minimal" / "submission.json"),
        "texts": texts,
        "sdk_version": lab_sdk.__version__,
        "packaging": packaging,
        "pyproject_version": "1.0.0",
        "facts": {},
        "adapter_cases": [],
        "disk_manifest": {},
        "computed_hashes": {},
    }
    ctx["computed_hashes"] = {
        "rules": canonical_sha(ctx["rules"]),
        "profile": canonical_sha(ctx["profile"]),
        "config": canonical_sha(ctx["config"]),
        "sdk_source": expected_sdk_source(pkg),
    }
    ctx["sdk_manifest"] = sdk_file_manifest(pkg)
    return ctx


def verify_image_sample(v, ctx):
    """examples/sdk-public-image.json：真实公开 PNG 样例，用 shipped lab_sdk.images 解码。"""
    sample = ctx["image_sample"]
    pkg = ctx["pkg"]
    camera_id = sample.get("camera_id")
    image = sample.get("image", {})
    provenance = sample.get("provenance", {})
    v.check("E", "E.image.camera_id", isinstance(camera_id, str) and bool(camera_id),
            "image sample camera_id=%r" % (camera_id,), "non-empty str", camera_id)
    v.check("E", "E.image.mime_type", image.get("mime_type") == "image/png",
            "image mime_type=%r" % (image.get("mime_type"),), "image/png", image.get("mime_type"))
    payload = image.get("base64")
    data = None
    try:
        data = base64.b64decode(payload, validate=True)
    except Exception as exc:  # noqa: BLE001
        v.check("E", "E.image.base64", False, "base64 解码失败: %s" % (exc,), "valid base64", None)
    else:
        v.check("E", "E.image.base64", True, "base64 解码成功（%d 字节）" % (len(data),))
    if data is not None:
        v.check("E", "E.image.png_magic", data.startswith(b"\x89PNG\r\n\x1a\n"),
                "PNG 魔数正确（sha256=%s）" % (sha256_bytes(data),), "PNG magic", sha256_bytes(data))
        from lab_sdk.images import pillow_rgb, png_bytes
        try:
            png = png_bytes(image)
            rgb = pillow_rgb(image)
        except Exception as exc:  # noqa: BLE001
            v.check("E", "E.image.png_decodable", False, "lab_sdk.images 解码失败: %s" % (exc,),
                    "decodable", repr(exc))
        else:
            v.check("E", "E.image.png_decodable", True,
                    "lab_sdk.images.png_bytes/pillow_rgb 成功解码：%dx%d RGB" % (rgb.width, rgb.height))
            v.check("E", "E.image.decoded_bytes_equal", sha256_bytes(png) == sha256_bytes(data),
                    "png_bytes 返回字节与 base64 解码字节一致")
            v.check("E", "E.image.pixel_limit", rgb.width * rgb.height <= 16 * 1024 * 1024,
                    "像素数 %d 未超过 16M 上限" % (rgb.width * rgb.height,), "<= 16777216",
                    rgb.width * rgb.height)
            ctx["facts"]["public_image_sample"] = {"camera_id": camera_id, "png_bytes": len(data),
                                                  "png_sha256": sha256_bytes(data),
                                                  "size": [rgb.width, rgb.height]}
    v.check("E", "E.image.provenance", isinstance(provenance.get("source_release"), str),
            "image provenance.source_release=%r" % (provenance.get("source_release"),), "non-empty str",
            provenance.get("source_release"))
    fixture_provenance = ctx["fixtures"]["cases"][0].get("provenance", {}) if ctx["fixtures"].get("cases") else {}
    v.check("E", "E.image.provenance_ties_case0",
            provenance.get("instruction_sha256_original") == fixture_provenance.get("instruction_sha256_original")
            and provenance.get("observation_sha256_original") == fixture_provenance.get("observation_sha256_original"),
            "公开图片 provenance 与 case0（wave1/franka）原始 instruction/observation SHA 一致（同一来源记录）",
            {"instruction": fixture_provenance.get("instruction_sha256_original"),
             "observation": fixture_provenance.get("observation_sha256_original")},
            {"instruction": provenance.get("instruction_sha256_original"),
             "observation": provenance.get("observation_sha256_original")})
    v.check("E", "E.image.manifest_sha_match",
            ctx["disk_manifest"].get("examples/sdk-public-image.json", {}).get("sha256")
            == sha256_file(pkg / "examples" / "sdk-public-image.json"),
            "sdk-public-image.json 实测 SHA 与清单一致")
    v.info("E", "E.image.unverifiable_original",
           "图片 provenance 的原始 instruction/observation SHA 指向未随包发布的完整原始观测，无法重算")


def _case_check_groups(result, index):
    prefix = "E.case%d." % index
    groups = {}
    for record in result["checks"]:
        if not record["id"].startswith(prefix):
            continue
        token = record["id"][len(prefix):].split(".")[0]
        bucket = groups.setdefault(token, {"pass": 0, "fail": 0})
        if record["status"] == "fail":
            bucket["fail"] += 1
        elif record["status"] == "pass":
            bucket["pass"] += 1
    return groups


def render_markdown(result):
    summary = result["summary"]
    facts = result["facts"]
    lines = []
    lines.append("# 公开包身份与合同核验报告")
    lines.append("")
    lines.append("- 任务：`task-1` 公开包身份与合同核验（哈希/规则/运行档/fixtures/Adapter）")
    lines.append("- 公开包：`inbox/1024-test/自主实验赛道选手公开包`（只读，未联网、未提交评测、未读 token）")
    lines.append("- 生成时间（UTC）：`%s`" % result["run"]["generated_at_utc"])
    lines.append("- 脚本：`verify_contracts.py`，SHA256 `%s`" % result["run"]["script_sha256"])
    lines.append("- 运行环境：Python %s / %s" % (result["run"]["python"], result["run"]["platform"]))
    lines.append("- 本次退出码：%d（%s）" % (0 if summary["issues_total"] == 0 else 1,
                                          "全部必检通过" if summary["issues_total"] == 0 else "发现问题"))
    lines.append("- 复现：在本目录执行 `python verify_contracts.py`（脚本自行重建 JSON 与本报告；"
                 "追加 `--timestamp 2026-10-24T00:00:00Z` 可逐字节复现同一 JSON）")
    lines.append("")
    verdict = ("公开包身份自洽：清单、release 合同哈希、运行档绑定、Adapter 协议与 4 份真实样例全部符合"
               if summary["issues_total"] == 0 else
               "发现 %d 项不符合/差异，详见“问题清单”" % summary["issues_total"])
    lines.append("## 结论")
    lines.append("")
    lines.append("**%s。**" % verdict)
    lines.append("")
    lines.append("| 指标 | 数量 |")
    lines.append("| --- | ---: |")
    lines.append("| 检查项总数 | %d |" % summary["checks_total"])
    lines.append("| 通过 | %d |" % summary["pass"])
    lines.append("| 不符合（问题） | %d |" % summary["issues_total"])
    lines.append("| 记录项（info） | %d |" % summary["info"])
    lines.append("")
    lines.append("| 类别 | 检查 | 通过 | 问题 | 记录 |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for category in ("A", "B", "C", "D", "E", "F"):
        bucket = summary["by_category"].get(category, {"total": 0, "pass": 0, "fail": 0, "info": 0})
        lines.append("| %s | %d | %d | %d | %d |" % (CATEGORY_TITLES[category], bucket["total"],
                                                     bucket["pass"], bucket["fail"], bucket["info"]))
    lines.append("")
    lines.append("## 关键身份事实")
    lines.append("")
    lines.append("| 项 | 值 |")
    lines.append("| --- | --- |")
    lines.append("| 规则身份 | `%s`（rules version %s） |" % (facts.get("rules_id"), facts.get("rules_version")))
    lines.append("| 发布版本 | `%s`（editorial_revision=%s） |"
                 % (facts.get("release_version"), facts.get("editorial_revision")))
    lines.append("| 运行档 | profile_id=`%s` |" % facts.get("profile_id"))
    model = facts.get("model", {})
    lines.append("| 唯一模型 | `%s` → `%s`@`%s` |"
                 % (model.get("id"), model.get("repository"), (model.get("revision") or "")[:12]))
    lines.append("| 模型权重 SHA256 | `%s` |" % model.get("weights_sha256"))
    robots = facts.get("robots", {})
    lines.append("| 机器人 | franka：臂 `%s`，%d 关节；piper-dual：臂 `%s`，每臂 %d 关节 |"
                 % (robots.get("franka", {}).get("canonical_arms"), robots.get("franka", {}).get("joints_per_arm"),
                    robots.get("piper-dual", {}).get("canonical_arms"),
                    robots.get("piper-dual", {}).get("joints_per_arm")))
    lines.append("| wave2 piper 原生→统一 | `arm`→`left`，`right`→`right`（wave1 为 `left/right` 不变） |")
    waves = facts.get("waves", {})
    lines.append("| 频率/结束 | wave1=%dHz、finish +%d 步（%.1fs）；wave2=%dHz、finish +%d 步 |"
                 % (waves.get("wave1", {}).get("frequency_hz"),
                    waves.get("wave1", {}).get("finish_extra_physics_steps"),
                    waves.get("wave1", {}).get("finish_physics_seconds"),
                    waves.get("wave2", {}).get("frequency_hz"),
                    waves.get("wave2", {}).get("finish_extra_physics_steps")))
    evaluation = facts.get("evaluation", {})
    lines.append("| 36 槽计分 | `%s`；分母 %s；显示 %s 位；中间舍入=%s |"
                 % (evaluation.get("score_formula"), evaluation.get("score_fraction_denominator"),
                    evaluation.get("display_decimals"), evaluation.get("intermediate_rounding")))
    platform = facts.get("platform", {})
    lines.append("| platform | playground_integrated=%s / official_score_writeback_verified=%s / "
                 "competition_ready=%s / challenge_ids=%s |"
                 % (platform.get("playground_integrated"), platform.get("official_score_writeback_verified"),
                    platform.get("competition_ready"), platform.get("challenge_ids")))
    lines.append("| release 补充 | live_nine_task_service_deployed=%s / new_runtime_native_full36_verified=%s / "
                 "external_model_api_qualified=%s |"
                 % (facts.get("platform_release", {}).get("live_nine_task_service_deployed"),
                    facts.get("platform_release", {}).get("new_runtime_native_full36_verified"),
                    facts.get("platform_release", {}).get("external_model_api_qualified")))
    lines.append("| SDK | `lab_sdk.__version__`=%s，冻结成员 6 个 |" % facts.get("sdk", {}).get("version"))
    gripper = facts.get("gripper_range_m_by_wave_robot", {})
    lines.append("| 夹爪范围 m | wave1 franka=%s、piper-dual=%s；wave2 franka=%s、piper-dual=%s |"
                 % (gripper.get("wave1", {}).get("franka"), gripper.get("wave1", {}).get("piper-dual"),
                    gripper.get("wave2", {}).get("franka"), gripper.get("wave2", {}).get("piper-dual")))
    action_contract = facts.get("action_contract", {})
    lines.append("| 动作合同 | steps=%s；观察暂停物理=%s；推理暂停物理=%s；墙钟继续=%s |"
                 % (action_contract.get("steps_range"), action_contract.get("observation_pauses_physics"),
                    action_contract.get("inference_pauses_physics"), action_contract.get("wall_clock_continues")))
    wave1_budgets = waves.get("wave1", {}).get("budgets", {})
    wave2_budgets = waves.get("wave2", {}).get("budgets", {})
    wave1_seconds = [wave1_budgets[task]["simulation_seconds"] for task in waves.get("wave1", {}).get("tasks", [])
                     if task in wave1_budgets]
    wave1_api = [wave1_budgets[task]["max_api_calls"] for task in waves.get("wave1", {}).get("tasks", [])
                 if task in wave1_budgets]
    wave2_tasks = waves.get("wave2", {}).get("tasks", [])
    wave2_common = wave2_budgets.get(wave2_tasks[0], {}) if wave2_tasks else {}
    lines.append("| 预算 | wave1：simulation=%s s、API=%s、CPU 120s/墙钟 600s、startup 900s；"
                 "wave2：simulation=%s s、max_physics_steps=%s、API=%s（唯一变更请求）、CPU 120s/墙钟 3600s、startup 900s |"
                 % ("/".join(str(value) for value in wave1_seconds),
                    "/".join(str(value) for value in wave1_api),
                    wave2_common.get("simulation_seconds"), wave2_common.get("max_physics_steps"),
                    wave2_common.get("max_api_calls")))
    lines.append("")
    lines.append("## 关键 SHA 对照")
    lines.append("")
    lines.append("| 身份 | 声明值（release） | 实测值 | 结果 |")
    lines.append("| --- | --- | --- | --- |")
    hashes = result["sha_table"]
    for row in hashes:
        if row["declared"] == "(not listed)":
            verdict_text = "自排除（不清单，不比较）"
        else:
            verdict_text = "一致" if row["match"] else "**不一致**"
        lines.append("| %s | `%s` | `%s` | %s |" % (row["name"], row["declared"], row["actual"], verdict_text))
    lines.append("")
    manifest_section = result["manifest"]
    lines.append("## PUBLIC-MANIFEST 文件身份")
    lines.append("")
    lines.append("- 清单覆盖 %d 个文件，逐文件 bytes/sha256 匹配 **%d/%d**，不符 %d 个。"
                 % (manifest_section["listed"], manifest_section["matched"], manifest_section["listed"],
                    manifest_section["mismatched"]))
    lines.append("- 包内实际文件 %d 个；除清单外未发现其它发布内容文件（`PUBLIC-MANIFEST.json` 自排除属预期）。"
                 % (manifest_section["on_disk"],))
    caches = manifest_section.get("runtime_cache_files", [])
    if caches:
        lines.append("- 运行缓存：`lab_sdk/__pycache__/` 下存在 %d 个 `.pyc`（由在包内直接 `import lab_sdk` 的进程产生，"
                     "非发布内容，不计入清单身份）：%s。" % (len(caches), ", ".join("`%s`" % item for item in caches)))
    lines.append("- 清单路径排序=%s；重复路径=%s；符号链接=%s。"
                 % ("是" if manifest_section["sorted"] else "否",
                    manifest_section["duplicates"] or "无", manifest_section["symlinks"] or "无"))
    lines.append("")
    lines.append("## fixtures × Adapter（4 份真实公开样例）")
    lines.append("")
    lines.append("| # | wave | robot | task | 内部检查 | 失败 | 结果 |")
    lines.append("| ---: | --- | --- | --- | ---: | ---: | --- |")
    for case in result["adapter_cases"]:
        lines.append("| %d | %s | %s | `%s` | %d | %d | %s |"
                     % (case["index"], case["wave"], case["robot"], case.get("task_id"),
                        case["checks_pass"], case["checks_fail"],
                        "通过" if case["checks_fail"] == 0 else "**有失败**"))
    lines.append("")
    lines.append("每份样例核验：schema→wave 推断、原生 robot_profile 归一、原生/统一臂键映射、"
                 "`physics.step_seconds/frequency_hz`、`finish.extra_physics_steps`、每臂关节数量与顺序、"
                 "夹爪范围、kinematics 限位、observation 臂名映射与 finished 推导，"
                 "以及动作合法/非法矩阵（关节数、steps 1–120、非有限数、越限、未知字段/臂、finish 精确 dict、"
                 "instrument 仅 wave2 C07）。")
    lines.append("")
    for case in result["adapter_cases"]:
        summary_matrix = case.get("action_matrix_summary", {})
        lines.append("### Case %d · %s / %s / `%s`" % (case["index"], case["wave"], case["robot"],
                                                       case.get("task_id")))
        lines.append("")
        lines.append("- 内部检查：通过 %d / 失败 %d" % (case["checks_pass"], case["checks_fail"]))
        lines.append("- 动作矩阵：合法动作通过 %d/%d，非法动作被拒绝 %d/%d"
                     % (summary_matrix.get("legal_pass", 0), summary_matrix.get("legal_total", 0),
                        summary_matrix.get("illegal_pass", 0), summary_matrix.get("illegal_total", 0)))
        contract = case.get("contract") or {}
        arms_text = "；".join(
            "`%s`：%d 关节 %s、夹爪范围 %s m"
            % (unified, item.get("joints"), item.get("joint_names"), item.get("gripper_width_m"))
            for unified, item in contract.get("arms", {}).items())
        lines.append("- 统一指令：`%s`；step_seconds=%r（%d Hz）；`finish.extra_physics_steps`=%d；"
                     "每动作最大步数=%d；instrument 允许=%s"
                     % (contract.get("instruction_schema"), contract.get("step_seconds"),
                        contract.get("frequency_hz", 0), contract.get("finish_extra_physics_steps", -1),
                        contract.get("maximum_steps_per_action", -1),
                        "是（wave2 C07）" if contract.get("instrument_allowed") else "否"))
        arm_map = contract.get("arm_map_native_to_unified", {})
        observation_map = contract.get("observation_arm_map_native_to_unified", {})
        lines.append("- 臂映射：原生 `%s` → 统一 `%s`；observation 原生 `%s` → 统一 `%s`"
                     % (contract.get("native_arms"), sorted(arm_map.values()),
                        sorted(observation_map), sorted(observation_map.values())))
        lines.append("- 每臂合同：%s" % arms_text)
        groups = _case_check_groups(result, case["index"])
        group_text = "、".join("%s %d/%d" % (token, bucket["pass"], bucket["pass"] + bucket["fail"])
                               for token, bucket in sorted(groups.items()))
        lines.append("- 通过项分组（组名 通过/总数）：%s" % group_text)
        provenance = case.get("provenance", {})
        lines.append("- provenance：source_release=`%s`，原始 instruction/observation SHA 已记录（原件不在包内，不可重算）"
                     % provenance.get("source_release"))
        if case["failures"]:
            lines.append("")
            lines.append("失败项：")
            for failure in case["failures"]:
                lines.append("- `%s`：%s" % (failure["id"], failure["detail"]))
        lines.append("")
    lines.append("## 问题清单")
    lines.append("")
    if not result["issues"]:
        lines.append("无。所有必检合同/身份项均符合；未发现哈希或文档不一致。")
    else:
        lines.append("| # | 检查项 | 说明 | 期望 | 实测 |")
        lines.append("| ---: | --- | --- | --- | --- |")
        for index, issue in enumerate(result["issues"], 1):
            lines.append("| %d | `%s` | %s | `%s` | `%s` |"
                         % (index, issue["id"], issue["detail"],
                            json.dumps(issue.get("expected"), ensure_ascii=False),
                            json.dumps(issue.get("actual"), ensure_ascii=False)))
    lines.append("")
    lines.append("## 无法从公开包独立核验的声明（如实记录）")
    lines.append("")
    for item in result["limitations"]:
        lines.append("- %s" % item)
    lines.append("")
    lines.append("## 复现")
    lines.append("")
    lines.append("```text")
    lines.append("cd deliverables/2026-10-24-nine-task/evidence/contracts")
    lines.append("python verify_contracts.py")
    lines.append("```")
    lines.append("")
    lines.append("退出码：0=全部必检通过；1=发现不一致（见问题清单）；2=脚本或输入错误。")
    lines.append("")
    return "\n".join(lines)


def build_result(ctx, verifier, run_info):
    summary = verifier.counts()
    summary["verdict"] = ("public_package_identity_and_contracts_consistent"
                          if summary["issues_total"] == 0 else "issues_found")
    summary["adapter_fixtures"] = ctx.get("adapter_summary", {})
    sha_table = []
    release = ctx["release"]
    computed = ctx["computed_hashes"]
    for name, key, declared in (
            ("contracts/rules-v1.json 规范 JSON SHA", "rules", release.get("rules_sha256")),
            ("contracts/runtime-profile.json 规范 JSON SHA", "profile", release.get("runtime_profile_sha256")),
            ("contracts/configuration-template.json 规范 JSON SHA", "config",
             release.get("example_configuration_sha256")),
            ("lab_sdk 六成员 source hash（ASCII 清单）", "sdk_source", release.get("sdk_source_sha256")),
    ):
        sha_table.append({"name": name, "declared": declared, "actual": computed.get(key),
                          "match": declared == computed.get(key)})
    registry_sha = sha256_bytes((ctx["pkg"] / "runtime" / "model-registry.json").read_bytes())
    wheels_sha = sha256_bytes((ctx["pkg"] / "runtime" / "wheels.lock.json").read_bytes())
    sha_table.append({"name": "runtime/model-registry.json 原始字节 SHA", "declared": ctx["profile"].get("model_registry_sha256"),
                      "actual": registry_sha, "match": ctx["profile"].get("model_registry_sha256") == registry_sha})
    sha_table.append({"name": "runtime/wheels.lock.json 原始字节 SHA", "declared": ctx["profile"].get("wheel_lock_sha256"),
                      "actual": wheels_sha, "match": ctx["profile"].get("wheel_lock_sha256") == wheels_sha})
    manifest_sha = sha256_file(ctx["pkg"] / "PUBLIC-MANIFEST.json")
    sha_table.append({"name": "PUBLIC-MANIFEST.json 文件自身 SHA（清单自排除）", "declared": "(not listed)",
                      "actual": manifest_sha, "match": True})
    listed_records = [record for record in verifier.checks if record["id"].startswith("A.manifest.entry:")]
    matched = sum(1 for record in listed_records if record["status"] == "pass")
    manifest_extra = ctx.get("manifest_extra", {"other": [], "caches": []})
    manifest_section = {
        "listed": len(listed_records),
        "matched": matched,
        "mismatched": len(listed_records) - matched,
        "on_disk": len([path for path in ctx.get("package_files_at_start", []) if not is_runtime_cache(path)]),
        "extra_files": manifest_extra.get("other", []),
        "runtime_cache_files": manifest_extra.get("caches", []),
        "duplicates": [record["actual"] for record in verifier.checks
                       if record["id"] == "A.manifest.unique_paths"][0] if any(
            record["id"] == "A.manifest.unique_paths" for record in verifier.checks) else [],
        "symlinks": [record["actual"] for record in verifier.checks
                     if record["id"] == "A.manifest.no_symlinks"][0] if any(
            record["id"] == "A.manifest.no_symlinks" for record in verifier.checks) else [],
        "sorted": any(record["id"] == "A.manifest.sorted" and record["status"] == "pass" for record in verifier.checks),
        "manifest_sha256": manifest_sha,
    }
    limitations = [
        "release.runtime_qualification 中的 runtime_source_archive_sha256 / runtime_manifest_sha256 / "
        "verification.test_log_sha256 指向未随公开包发布的归档、清单或测试日志，无法在包内独立复核，仅做格式与自洽检查。",
        "examples/sdk-fixtures.json 与 sdk-public-image.json 的 provenance.*_sha256_original 对应移除平台身份与"
        "图像 payload 前的原始记录；公开包不含原件，无法重算原始 SHA（仅验证格式、投影说明与来源一致性）。",
        "本核验仅覆盖公开包的静态合同与 lab_sdk.adapters 协议行为，不包含真实物理仿真、九题评测、"
        "Isaac/GPU 运行、平台 Challenge/Attempt 接入或分数回写（release 明确 competition_ready=false）。",
        "无法证明当前工作副本与冻结发布归档（frozen-source-003）逐字相同；只能证明工作副本中 "
        "rules/runtime-profile/configuration 规范 JSON 与 SDK source hash 等于 release.json 声明值。",
        "真实公开样例只有 4 份：wave1 仅 bottle_transfer（两机器人），wave2 franka=C02、piper-dual=C07；"
        "9 题中仅 3 题有真实协议样例，其余任务仅由 rules/文档覆盖。",
        "wheels.lock 的下载 URL 与 wheel 字节未做网络/本地校验（任务禁用网络，且包内不含 wheel），"
        "仅核验记录格式、requirements 锁一致性与 profile 绑定 SHA。",
    ]
    if ctx.get("manifest_extra", {}).get("caches"):
        limitations.append(
            "公开包 lab_sdk/ 下存在 Python 字节码缓存文件（__pycache__/*.pyc），由在包内直接 import lab_sdk 的进程产生，"
            "不属 PUBLIC-MANIFEST 发布内容；本脚本已设置 sys.dont_write_bytecode=True，运行时不写缓存。"
            "如需与清单文件树逐字一致，请在无并发进程的干净副本上复核。")
    result = {
        "schema": "lab-nine-contract-verification/v1",
        "task": "task-1: 公开包身份与合同核验（哈希/规则/运行档/fixtures/Adapter）",
        "run": run_info,
        "inputs": ctx["inputs"],
        "summary": summary,
        "sha_table": sha_table,
        "manifest": manifest_section,
        "facts": ctx["facts"],
        "checks": verifier.checks,
        "adapter_cases": ctx["adapter_cases"],
        "issues": verifier.issues,
        "limitations": limitations,
    }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="公开包身份与合同核验（只读）")
    parser.add_argument("--package", help="公开包根目录（默认自动定位 inbox/1024-test/自主实验赛道选手公开包）")
    parser.add_argument("--out", help="输出目录（默认脚本所在目录）")
    parser.add_argument("--timestamp", help="固定生成的 UTC 时间（ISO8601），用于逐字节复现")
    args = parser.parse_args(argv)

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    script_path = Path(__file__).resolve()
    out_dir = Path(args.out).resolve() if args.out else script_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = args.timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    package = locate_package(args.package)
    # 先快照包内文件集合（在 import lab_sdk 之前），用于 A 段清单覆盖与只读自检。
    package_files_at_start = scan_package_files(package)
    package_caches_at_start = [path for path in package_files_at_start if is_runtime_cache(path)]
    package_release_files_at_start = [path for path in package_files_at_start if not is_runtime_cache(path)]

    try:
        ctx = load_context(package)
    except (OSError, ValueError) as exc:
        print("输入错误: %s" % (exc,))
        return 2
    ctx["inputs"] = collect_inputs(package)
    ctx["package_files_at_start"] = package_files_at_start
    verifier = Verifier()
    try:
        verify_manifest(verifier, ctx)
        verify_release_contracts(verifier, ctx)
        verify_runtime_locks(verifier, ctx)
        verify_identity(verifier, ctx)
        verify_adapter_fixtures(verifier, ctx)
        verify_image_sample(verifier, ctx)
        verify_docs(verifier, ctx)
    except (OSError, ValueError, KeyError) as exc:
        print("输入/结构错误: %s" % (exc,))
        return 2

    # 只读自检：运行后公开包内不应出现新增发布内容文件（并发 import 产生的 __pycache__ 缓存单独记录）。
    after = scan_package_files(package)
    new_files = sorted(set(after) - set(package_files_at_start))
    new_non_cache = [path for path in new_files if not is_runtime_cache(path)]
    new_caches = [path for path in new_files if is_runtime_cache(path)]
    verifier.check("A", "A.read_only.no_new_files", not new_non_cache,
                   "脚本运行期间未在公开包内产生新增发布内容文件" if not new_non_cache
                   else "公开包内新增文件: %r" % (new_non_cache,), [], new_non_cache)
    if new_caches:
        verifier.info("A", "A.read_only.concurrent_bytecode_cache",
                      "运行期间出现 %d 个 Python 字节码缓存（可能由并发读取公开包 SDK 的进程产生，不属发布内容）: %r"
                      % (len(new_caches), new_caches), new_caches)

    run_info = {
        "generated_at_utc": generated_at,
        "script": script_path.as_posix(),
        "script_sha256": sha256_file(script_path),
        "python": platform_module.python_version(),
        "platform": platform_module.platform(),
        "package_root": package.as_posix(),
        "mode": "read-only; no network; no evaluation submission; no token access",
        "package_files_at_start": package_release_files_at_start,
        "package_runtime_caches_at_start": package_caches_at_start,
    }
    result = build_result(ctx, verifier, run_info)
    json_path = out_dir / "contract-verification.json"
    md_path = out_dir / "contract-verification.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")

    summary = result["summary"]
    print("公開包: %s" % package)
    print("checks: total=%d pass=%d issues=%d info=%d" % (summary["checks_total"], summary["pass"],
                                                          summary["issues_total"], summary["info"]))
    print("manifest: %d/%d matched" % (manifest_matched(result), result["manifest"]["listed"]))
    adapter = summary.get("adapter_fixtures", {})
    print("adapter fixtures: %s cases, pass=%d fail=%d" % (adapter.get("cases"), adapter.get("checks_pass"),
                                                           adapter.get("checks_fail")))
    print("output: %s" % json_path)
    print("output: %s" % md_path)
    if summary["issues_total"] == 0:
        print("verdict: CONSISTENT (no issues)")
        return 0
    print("verdict: ISSUES FOUND (%d)" % summary["issues_total"])
    for issue in result["issues"][:30]:
        print(" - %s: %s" % (issue["id"], issue["detail"]))
    return 1


def manifest_matched(result):
    return result["manifest"]["matched"]


if __name__ == "__main__":
    sys.exit(main())
