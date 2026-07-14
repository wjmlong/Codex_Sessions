from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


FORMAT_VERSION = 1
MANAGED_DIRS = ("sessions", "archived_sessions", "attachments")
MANAGED_FILES = (
    "session_index.jsonl",
    "state_5.sqlite",
    "goals_1.sqlite",
    "memories_1.sqlite",
    "thread_history_1.sqlite",
    ".codex-global-state.json",
    "sqlite/codex-dev.db",
)
SQLITE_FILES = {
    "state_5.sqlite",
    "goals_1.sqlite",
    "memories_1.sqlite",
    "thread_history_1.sqlite",
    "sqlite/codex-dev.db",
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
        result = destination_connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(f"SQLite integrity check failed for {source}")
    finally:
        destination_connection.close()
        source_connection.close()


def copy_complete_jsonl(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_handle, destination.open("wb") as output_handle:
        pending = b""
        while True:
            chunk = input_handle.read(1024 * 1024)
            if not chunk:
                break
            pending += chunk
            boundary = pending.rfind(b"\n")
            if boundary >= 0:
                output_handle.write(pending[: boundary + 1])
                pending = pending[boundary + 1 :]


def copy_snapshot_file(source: Path, destination: Path, relative_path: str) -> None:
    if relative_path in SQLITE_FILES:
        sqlite_backup(source, destination)
    elif source.suffix.lower() == ".jsonl":
        copy_complete_jsonl(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def build_staging(codex_home: Path, staging_root: Path) -> dict:
    snapshot_root = staging_root / "codex"
    copied: list[Path] = []
    for directory_name in MANAGED_DIRS:
        source_directory = codex_home / directory_name
        if not source_directory.exists():
            continue
        for source in sorted(path for path in source_directory.rglob("*") if path.is_file()):
            relative = source.relative_to(codex_home).as_posix()
            destination = snapshot_root / Path(relative)
            copy_snapshot_file(source, destination, relative)
            copied.append(destination)
    for relative in MANAGED_FILES:
        source = codex_home / Path(relative)
        if not source.is_file():
            continue
        destination = snapshot_root / Path(relative)
        copy_snapshot_file(source, destination, relative)
        copied.append(destination)
    entries = []
    for path in sorted(copied):
        entries.append(
            {
                "path": path.relative_to(snapshot_root).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_host": platform.node(),
        "files": entries,
    }
    (staging_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def create_archive(codex_home: Path, output: Path) -> dict:
    codex_home = codex_home.resolve()
    if not codex_home.is_dir():
        raise FileNotFoundError(f"Codex home not found: {codex_home}")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_name(f".{output.name}.{utc_stamp()}.tmp")
    with tempfile.TemporaryDirectory(prefix="codex-session-snapshot-") as temporary:
        staging_root = Path(temporary)
        manifest = build_staging(codex_home, staging_root)
        with zipfile.ZipFile(
            temporary_output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for path in sorted(item for item in staging_root.rglob("*") if item.is_file()):
                archive.write(path, path.relative_to(staging_root).as_posix())
    os.replace(temporary_output, output)
    result = {
        "archive": str(output),
        "archive_size": output.stat().st_size,
        "archive_sha256": sha256_file(output),
        "file_count": len(manifest["files"]),
    }
    return result


def safe_archive_names(archive: zipfile.ZipFile) -> None:
    for name in archive.namelist():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError(f"Unsafe archive member: {name}")


def verify_archive(archive_path: Path) -> dict:
    with zipfile.ZipFile(archive_path, "r") as archive:
        safe_archive_names(archive)
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format_version") != FORMAT_VERSION:
            raise RuntimeError("Unsupported snapshot format")
        names = set(archive.namelist())
        for entry in manifest.get("files", []):
            archive_name = f"codex/{entry['path']}"
            if archive_name not in names:
                raise RuntimeError(f"Missing archive member: {archive_name}")
            digest = hashlib.sha256()
            size = 0
            with archive.open(archive_name) as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
            if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                raise RuntimeError(f"Snapshot verification failed: {entry['path']}")
    return {
        "archive": str(archive_path.resolve()),
        "file_count": len(manifest["files"]),
        "created_at": manifest["created_at"],
        "source_host": manifest["source_host"],
    }


def running_codex_processes() -> list[str]:
    if os.name != "nt":
        return []
    completed = subprocess.run(
        ["tasklist", "/fo", "csv", "/nh"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    blocked_names = {
        "chatgpt.exe",
        "codex.exe",
        "codex-plus-plus.exe",
        "codex-plus-plus-manager.exe",
    }
    found = set()
    for line in completed.stdout.splitlines():
        executable = line.strip().lstrip('"').split('",', 1)[0].lower()
        if executable in blocked_names:
            found.add(executable)
    return sorted(found)


def remove_sqlite_sidecars(codex_home: Path) -> None:
    for relative in SQLITE_FILES:
        path = codex_home / Path(relative)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{path}{suffix}")
            if sidecar.exists():
                sidecar.unlink()


def restore_archive(archive_path: Path, codex_home: Path, skip_pre_restore: bool) -> dict:
    processes = running_codex_processes()
    if processes:
        raise RuntimeError(
            "Close Codex, ChatGPT, and Codex++ before restore: " + ", ".join(processes)
        )
    verification = verify_archive(archive_path)
    codex_home = codex_home.resolve()
    codex_home.mkdir(parents=True, exist_ok=True)
    pre_restore_archive = None
    has_existing_data = any((codex_home / name).exists() for name in MANAGED_DIRS + MANAGED_FILES)
    if has_existing_data and not skip_pre_restore:
        backup_directory = Path.home() / ".codex-session-sync-backups"
        pre_restore_archive = backup_directory / f"pre-restore-{utc_stamp()}.zip"
        create_archive(codex_home, pre_restore_archive)
    with tempfile.TemporaryDirectory(prefix="codex-session-restore-") as temporary:
        staging_root = Path(temporary)
        with zipfile.ZipFile(archive_path, "r") as archive:
            safe_archive_names(archive)
            archive.extractall(staging_root)
        snapshot_root = staging_root / "codex"
        for directory_name in MANAGED_DIRS:
            destination = codex_home / directory_name
            if destination.exists():
                shutil.rmtree(destination)
            source = snapshot_root / directory_name
            if source.exists():
                shutil.copytree(source, destination)
        for relative in MANAGED_FILES:
            destination = codex_home / Path(relative)
            if destination.exists():
                destination.unlink()
            source = snapshot_root / Path(relative)
            if source.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
    remove_sqlite_sidecars(codex_home)
    return {
        "restored_to": str(codex_home),
        "source_created_at": verification["created_at"],
        "file_count": verification["file_count"],
        "pre_restore_archive": str(pre_restore_archive) if pre_restore_archive else None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-home", type=Path, default=default_codex_home())
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--output", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--archive", type=Path, required=True)
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--archive", type=Path, required=True)
    restore_parser.add_argument("--skip-pre-restore-backup", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "backup":
        result = create_archive(args.codex_home, args.output)
    elif args.command == "verify":
        result = verify_archive(args.archive)
    else:
        result = restore_archive(
            args.archive, args.codex_home, args.skip_pre_restore_backup
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

