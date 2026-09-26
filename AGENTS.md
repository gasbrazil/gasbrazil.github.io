# GasBrazil.com — agent notes

## Git workflow (required)

Before **any** push to a feature branch:

1. `git fetch origin main`
2. Update your branch with the latest `main`:
   - **Preferred:** `git pull origin main --rebase` (while on the feature branch), or
   - `git merge origin/main` if rebase is unsafe for that branch.
3. Resolve conflicts, run tests, then push.

After a PR is **merged**, do not keep pushing to the old PR branch assuming it is still open. Start from fresh `origin/main` (new branch or reset) before follow-up work.

Use `git push -u origin <branch>` only when the branch is current with `main` (or the intended base).

## Python environment

Ensure dependencies are installed using `uv` (recommended) or `pip`:

```bash
uv sync --all-extras
# or: pip install -e ".[dev]"
```

Run Python with your active environment (e.g. `uv run python ...` or `python ...`).

## Dashboard HTML shells

Shared chrome/theme changes live in `shared/theme.css` and `shared/dashboard_kit.py`. Regenerate committed shells when needed:

```bash
python shared/resync_built_shells.py
```

`resync_built_shells.py` resyncs all dashboard shells as well as the hub (`home`, `about`, `404`, `admin`). When running locally without R2 or data lake access, `build_home.py` automatically preserves committed sparklines, KPI metrics, and CDN artifact URLs.

Individual dashboards can also be rebuilt with `python <site>/dashboard.py` when parquet/data is available.
