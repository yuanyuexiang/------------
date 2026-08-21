# Repository Guidelines

## Project Structure & Module Organization

Jinbang is a monorepo for a State Grid tender-document workflow. `apps/jb_api/` contains the thin FastAPI HTTP layer; keep business logic out of routes. `apps/jb-web/` is the React, TypeScript, Vite, and Ant Design frontend. Parsing logic lives in `packages/jb_parser/`, with `pipeline.py` coordinating archive unpacking, classification, extraction, normalization, scoring, and TRM construction. Tests are under `tests/`, deployment files under `deploy/`, and product research and plans under `docs/`.

The local `物资/` and `服务/` directories contain large, sensitive regression fixtures. They are intentionally ignored by Git and must not be copied into source or commits.

## Architecture Expectations

Preserve the "thin API, thick domain package" boundary. Deterministic parsing and validation belong in reusable packages, not HTTP handlers or React components. Treat the TRM as the canonical representation of tender requirements. Prefer explicit warnings or `None` for missing facts; never invent values during extraction.

## Build, Test, and Development Commands

- `pip install -e ".[dev]"` installs Python packages and developer tools.
- `jb-parse input.zip -o trm.json` parses a tender package from the CLI.
- `pytest -q` runs the Python regression suite.
- `ruff check .` checks Python formatting, imports, and lint rules.
- `uvicorn jb_api.main:app --reload --port 8000` starts the API.
- `npm install --prefix apps/jb-web` installs frontend dependencies.
- `npm run dev --prefix apps/jb-web` starts Vite on port 5173.
- `npm run build --prefix apps/jb-web` type-checks and builds the frontend.
- `docker compose up -d --build` starts the local application stack.

## Coding Style & Naming Conventions

Use four spaces in Python, type annotations, Pydantic models, and a 100-character line target. Python modules and packages use `snake_case`; React components use `PascalCase`, variables use `camelCase`, and npm projects use `kebab-case`. Keep extraction functions small and source-specific. Run Ruff before committing.

## Testing Guidelines

Use pytest and name files `test_*.py` and functions `test_*`. Add unit tests for deterministic rules and regression tests for every supported document variant. Tests requiring local fixtures must use `pytest.mark.skipif` when samples are unavailable. Do not weaken existing real-sample assertions to accommodate regressions.

## Commit & Pull Request Guidelines

History uses concise, outcome-oriented commit subjects, usually in Chinese, such as `S1 推进：...` or `架构规范化：...`. Keep each commit focused. Pull requests should explain scope, affected samples, verification commands, and known limitations; include screenshots for UI changes and example TRM diffs for parser changes. Never commit `.env`, ZIP inputs, generated output, credentials, or customer data.
