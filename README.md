# Codex Sessions

Codex Desktop session bundles synchronized with [Codex Session Toolkit](https://github.com/lyston11/codex-session-toolkit).

The repository currently contains 33 validated Desktop session bundles exported from `LAPTOP-2GMBRRQA`.

Browse the sessions by project and readable title in [SESSION_CATALOG.md](SESSION_CATALOG.md). Imported Codex sidebar titles use the format `[项目名] 对话名`.

## Source device

Toolkit is installed at:

```text
C:\Users\kiki\codex-session-toolkit
```

Export and push the latest sessions:

```powershell
cd C:\Users\kiki\codex-session-toolkit
.\.venv\Scripts\codex-session-toolkit.cmd export-desktop-all --skills-mode skip
python C:\Users\kiki\Codex_Sessions\scripts\refresh-session-catalog.py
.\.venv\Scripts\codex-session-toolkit.cmd validate-bundles
.\.venv\Scripts\codex-session-toolkit.cmd sync-github --branch main --message "Sync Codex session bundles"
```

GitHub access on this machine uses the Toolkit-local proxy `http://127.0.0.1:7897`. It does not change global Git proxy settings.

## Destination Windows device

Install Git, Python 3, and GitHub CLI, then clone this repository and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-toolkit-windows.ps1
```

If GitHub requires the local Clash proxy:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-toolkit-windows.ps1 -ProxyUrl http://127.0.0.1:7897
```

The setup script installs the Toolkit, applies the nested sub-agent session compatibility patch, connects this repository, pulls the bundles, and validates them.

After setup, close Codex completely and start the Toolkit:

```powershell
& "$env:USERPROFILE\codex-session-toolkit\codex-session-toolkit.cmd"
```

Use `Bundle / Transfer -> 导入 Bundle 为会话`, select the desired bundles, and import them with Desktop visibility enabled. For all sessions, filter to the latest Desktop batch, press `a`, then `i`.

When the project path differs between devices, use the Toolkit project-path mapping during import.

## Compatibility patch

Codex sub-agent rollout files can contain their own primary `session_meta` followed by embedded parent-thread `session_meta` records. Toolkit 1.0.0 incorrectly rejected those files because it required every embedded `session_meta` ID to match the child rollout filename.

`patches/toolkit-nested-session-meta.patch` changes validation to require only the primary session metadata to match. The source device uses the same patch, and all 33 bundles pass Toolkit validation.
