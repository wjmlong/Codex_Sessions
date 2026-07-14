from __future__ import annotations

import argparse
import json
import re
import shlex
import sqlite3
from collections import defaultdict
from pathlib import Path


TITLE_OVERRIDES = {
    "019f41c1-b45b-7fc0-bf80-8f270e194318": "规划 ReHealth Android 真实数据 MVP",
    "019f41c4-09b9-7063-9829-00e90fc62b22": "分析核心算法仓库接入",
    "019f41c4-398f-70d3-ae78-e9f3c05d8a58": "评估 ReHealth 后端仓库",
    "019f41c4-547d-7031-b6de-60146f7ae2c1": "评估 Android 工程与测试方案",
    "019f448f-c0b2-7890-bba5-5abd719c14eb": "评估 ReHealth Android MVP 工程",
    "019f44a7-5730-79d1-becd-a54f593b62f7": "检查 Android 构建健康",
    "019f44df-d968-7930-88f7-dd4d1f782dce": "实现 Android 特征提取器",
    "019f44fa-f33e-7ef0-bcc2-10065c399c5c": "接入模型服务 F1",
    "019f45b3-cd47-7671-a0bc-6e43c317840b": "修复 ZCODE extra_body 参数错误",
    "019f45d8-196a-7252-84dd-10502ad9328a": "后端模块选型与数据库拆分",
    "019f46d4-7745-7a40-ae3e-95c1560e6f84": "实现 Android BLE 后台采集",
    "019f46e8-8001-7613-8282-639bfb328878": "QA 发布验收",
    "019f4738-2c68-7751-af4c-6a2b7ca3dc38": "修复 D1 状态与工程一致性",
    "019f473d-6f4c-74b3-b32a-408bc02b4b8f": "ReHealth MVP 工程总评估",
    "019f475c-967b-7cf0-99ed-accbafde5d71": "接入 Android 标准风险 UI 路径",
    "019f476e-76d6-77b3-835b-342731dda418": "下线后端遗留路径",
    "019f5a18-0183-74f3-8193-89a832ddfa31": "同步 Codex 会话与工程进度",
    "019f5c2b-f9c8-7aa0-b8fa-286b9ebea3fa": "子 Agent：UI 静态数据审计",
    "019f5c2c-25e2-7ff3-869c-f6151534eae3": "子 Agent：原厂 XAPK 协议审计",
    "019f5c2c-67a5-7c50-b0c4-d706642795ec": "子 Agent：CVD16 功能审计",
    "019f5c38-cac3-7280-98f9-4fb47729fd4d": "子 Agent：安装原厂 XAPK",
    "019f5c39-0dc9-7471-825e-1f2cfb891f82": "子 Agent：修复 APK 启动图标",
    "019f5c39-4e68-7600-b85e-ee21735fc481": "子 Agent：接入本地 GPT 问答",
}


def parse_manifest(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        try:
            parsed = shlex.split(raw, posix=True)
            values[key] = parsed[0] if parsed else ""
        except ValueError:
            values[key] = raw.strip("'\"")
    return values


def update_manifest_title(path: Path, title: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    replacement = f"THREAD_NAME={shlex.quote(title)}"
    updated = False
    for index, line in enumerate(lines):
        if line.startswith("THREAD_NAME="):
            lines[index] = replacement
            updated = True
            break
    if not updated:
        lines.append(replacement)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_index_names(codex_home: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    path = codex_home / "session_index.jsonl"
    if not path.is_file():
        return names
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        session_id = str(entry.get("id") or "")
        name = str(entry.get("thread_name") or "").strip()
        if session_id and name:
            names[session_id] = name
    return names


def load_thread_metadata(codex_home: Path) -> dict[str, dict[str, str]]:
    path = codex_home / "state_5.sqlite"
    if not path.is_file():
        return {}
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {
            str(session_id): {"title": str(title or ""), "cwd": str(cwd or "")}
            for session_id, title, cwd in connection.execute("SELECT id, title, cwd FROM threads")
        }
    finally:
        connection.close()


def clean_path(path: str) -> str:
    return path.removeprefix("\\\\?\\").rstrip("\\/")


def project_name(cwd: str) -> str:
    normalized = clean_path(cwd).lower()
    if "daily-stock-analysis" in normalized:
        return "Daily Stock Analysis"
    if "github-app-connector" in normalized and "rehealth" in normalized:
        return "ReHealth GitHub 评估"
    if normalized == "d:\\rehealthai" or normalized.startswith("d:\\rehealthai\\"):
        return "ReHealth AI"
    if normalized == str(Path.home()).lower():
        return "Codex 本机配置"
    name = Path(clean_path(cwd)).name
    return name or "未分类项目"


def readable_title(session_id: str, index_names: dict[str, str], db_title: str) -> str:
    if session_id in TITLE_OVERRIDES:
        return TITLE_OVERRIDES[session_id]
    candidate = index_names.get(session_id) or db_title
    candidate = re.sub(r"\s+", " ", candidate).strip()
    candidate = re.sub(r"\[([^]]+)]\([^)]+\)", r"\1", candidate)
    if len(candidate) > 48:
        candidate = candidate[:47].rstrip(" ，。,:：;；-") + "…"
    return candidate or f"会话 {session_id[:8]}"


def build_catalog(repo_root: Path, codex_home: Path) -> list[dict[str, str]]:
    index_names = load_index_names(codex_home)
    metadata = load_thread_metadata(codex_home)
    records: list[dict[str, str]] = []
    for manifest in sorted(repo_root.rglob("manifest.env")):
        values = parse_manifest(manifest)
        session_id = values.get("SESSION_ID", "")
        if not session_id:
            continue
        thread = metadata.get(session_id, {})
        cwd = thread.get("cwd") or values.get("SESSION_CWD", "")
        project = project_name(cwd)
        title = readable_title(session_id, index_names, thread.get("title", ""))
        display_title = f"[{project}] {title}"
        update_manifest_title(manifest, display_title)
        records.append(
            {
                "id": session_id,
                "project": project,
                "title": title,
                "display_title": display_title,
                "cwd": clean_path(cwd),
                "updated_at": values.get("UPDATED_AT", ""),
                "bundle": manifest.parent.relative_to(repo_root).as_posix(),
            }
        )
    return records


def write_catalog(repo_root: Path, records: list[dict[str, str]]) -> None:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for record in records:
        grouped[record["project"]].append(record)
    lines = [
        "# Codex 会话目录",
        "",
        f"共 {len(records)} 条已验证会话，按项目和更新时间分组。导入 Codex 后显示标题采用 `[项目名] 对话名`。",
        "",
    ]
    for project in sorted(grouped):
        project_records = sorted(
            grouped[project], key=lambda item: item["updated_at"], reverse=True
        )
        lines.extend(
            [
                f"## {project}（{len(project_records)}）",
                "",
                "| 对话名 | 更新时间 | Session ID |",
                "| --- | --- | --- |",
            ]
        )
        for record in project_records:
            title = record["title"].replace("|", "\\|")
            updated_at = record["updated_at"].replace("T", " ").replace("Z", " UTC")
            link = f"[{record['id']}]({record['bundle']})"
            lines.append(f"| {title} | {updated_at} | {link} |")
        lines.append("")
    (repo_root / "SESSION_CATALOG.md").write_text("\n".join(lines), encoding="utf-8")
    (repo_root / "session-catalog.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    args = parser.parse_args()
    repo_root = args.repo.resolve()
    records = build_catalog(repo_root, args.codex_home.resolve())
    write_catalog(repo_root, records)
    print(f"Updated {len(records)} session titles and wrote SESSION_CATALOG.md")


if __name__ == "__main__":
    main()
