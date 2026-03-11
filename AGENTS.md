# Repository Guidelines

## Project Structure & Module Organization
Core FastAPI entrypoints live in `app/main.py`, while REST routes and orchestration logic sit in `biz/routes` and `biz/services`. Engine-specific code resides under `core/asr`, `core/ai`, and `core/audio`, and web assets ship from `public/` with data samples in `data/`. Automation helpers live in `scripts/` and `commands/beta/*` (CLI flows such as `video2txt.py`), and integration docs or specs are stored in `docs/`. Tests belong in `tests/`, with heavy model fixtures isolated inside `tests/models` to keep git history small.

## Build, Test & Development Commands
- `pip install -r requirements.txt` — install Python and ML dependencies; rerun after syncing the repo.
- `python app/main.py` — boot the FastAPI service together with the Vue assets served from `public/` (default http://127.0.0.1:19080).
- `python commands/beta/3.0/video2txt.py -i sample.mp4` — run the latest CLI workflow end to end.
- `pytest -q` — execute the unit and service tests (pytest is configured via `pytest.ini` to add legacy `src` paths to `PYTHONPATH`).

## Coding Style & Naming Conventions
Use Python 3.10+ with 4-space indentation, type hints on public functions, and snake_case variables. Run `black app biz core scripts tests` before pushing and ensure `flake8` passes with the default config in `requirements.txt`. Prefer descriptive module names (e.g., `asr_engine.py` vs. `utils2.py`) and keep FastAPI route handlers in `biz/routes` named `verb_object.py` such as `post_transcription.py`.

## Testing Guidelines
Target meaningful coverage for any new engine, route, or CLI option; provide lightweight model stubs when touching ASR logic. Use `pytest -k keyword` while iterating and place fixtures under `tests/conftest.py` or `tests/models`. Name tests `test_<feature>_<behavior>` to match pytest discovery and include regression cases for every bug fix.

## Commit & Pull Request Guidelines
Follow the informal Conventional Commits pattern already in git history (`feat: 会议优化+代码优化`, `fix: ...`, `chore: ...`). Each PR should describe scope, testing evidence, and any FFmpeg/GPU assumptions; attach CLI transcripts or screenshots for UI-facing work. Reference GitHub issues with `Closes #123` where applicable and request review once CI (`pytest`, `flake8`, `black --check`) is green.

## Environment & Configuration Tips
Ensure FFmpeg is on your PATH before running conversions (`brew install ffmpeg` or `sudo apt install ffmpeg`). Keep large checkpoints out of git by storing them under `cache/` or `data/` paths already ignored by `.gitignore`. Use `.env` or `config/*.yaml` for secrets; never hard-code API keys in commit history. When experimenting with GPU builds, document driver/CUDA specifics in the PR body so reviewers can reproduce.
