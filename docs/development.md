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
