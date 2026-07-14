# Codex Sessions

Private, versioned snapshots for moving Codex sessions between Windows devices.

## Security

The upload script refuses to run unless `wjmlong/Codex_Sessions` is private. Codex sessions can contain source code, prompts, local paths, and secrets pasted into conversations.

Authentication files are never included. Configure Codex and Codex++ API credentials separately on every device.

## Snapshot contents

- `~/.codex/sessions`
- `~/.codex/archived_sessions`
- `~/.codex/attachments`
- `~/.codex/session_index.jsonl`
- `~/.codex/sqlite/codex-dev.db`
- `~/.codex/state_5.sqlite`
- `~/.codex/goals_1.sqlite`
- `~/.codex/memories_1.sqlite`
- `~/.codex/thread_history_1.sqlite`, when present
- `~/.codex/.codex-global-state.json`

SQLite files are copied with SQLite's online backup API. JSONL files are copied only through their last complete line. `auth.json`, `config.toml`, logs, caches, browser state, and sandbox state are excluded.

`codex-dev.db` is only the desktop app's local thread catalog. Complete resumable sessions also require the JSONL rollout files and `state_5.sqlite`, so the scripts back up all three layers.

## First-time setup

1. Change this GitHub repository to private.
2. Install Codex, Codex++, GitHub CLI, and sign in with `gh auth login` on both devices.
3. Keep project paths identical on both devices when possible, such as `D:\rehealthAI`.

## Upload from the source device

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync-to-github.ps1
```

The script replaces two assets on the `codex-sessions-latest` GitHub Release:

- `codex-sessions-latest.zip`
- `codex-sessions-latest.sha256`

Using a release asset avoids committing a new binary database version on every sync.

## Restore on the destination device

Install and launch Codex once, then close Codex, ChatGPT, Codex++, and the Codex++ manager completely. Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore-from-github.ps1
```

The restore script verifies the SHA-256 checksum and archive manifest. Existing managed session data is saved to `~/.codex-session-sync-backups` before replacement.

Do not work on both devices concurrently. Upload from the device you are leaving, then restore on the device you are moving to.

## Local commands

```powershell
python .\scripts\codex_sessions.py backup --output .\codex-sessions.zip
python .\scripts\codex_sessions.py verify --archive .\codex-sessions.zip
python .\scripts\codex_sessions.py restore --archive .\codex-sessions.zip
```

