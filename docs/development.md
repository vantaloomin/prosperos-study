# Development

[Back to the README](../README.md)

Run these commands from the repository root.

The interface uses React, TypeScript, and Vite. The local backend uses Python, FastAPI, and SQLite.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
npm.cmd ci
```

For development, run the backend and Vite in separate terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn server.main:create_app --factory --host 127.0.0.1 --port 8765
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. Vite forwards API requests to the local backend. The production launcher serves the built interface and API together on port 8765.

Run the project checks with:

```powershell
powershell -ExecutionPolicy Bypass -File .\check.ps1
```

The checks cover backend tests, frontend model tests, Python/TypeScript linting, and the production build. Both complexity linters enforce a maximum of 10 per function. Tests use isolated data; keep the user's story database out of fixtures. The `ROLEPLAY_DB` environment variable selects an alternate database.

Source lives in `src/`, `server/`, `tests/`, and `scripts/`. Local data, agent files, planning archives, installed dependencies, and generated output are excluded from Git.

Follow [the contribution and file-placement rules](../CONTRIBUTING.md) for humans and coding agents. Keep temporary goals and checkpoints in ignored `planning/` folders, raw output in `test-results/`, and maintained user documentation in `docs/`. Release notes summarize measured checks and limitations.

For a quick documentation-only check, run `python scripts/check_repository.py`; use `--staged` to validate the exact publication snapshot. `check.ps1` runs the working-tree check first, and the Repository hygiene GitHub workflow checks pushes and pull requests. The check has no third-party dependencies and also supports extracted source ZIPs.
