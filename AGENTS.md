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

## Python

Use the repo venv: `/workspace/.venv/bin/python` (not bare `python`).

## Dashboard HTML shells

Shared chrome/theme changes live in `shared/theme.css` and `shared/dashboard_kit.py`. Regenerate committed shells when needed:

```bash
/workspace/.venv/bin/python build_home.py
/workspace/.venv/bin/python shared/resync_built_shells.py
```

Individual dashboards can also be rebuilt with `python <site>/dashboard.py` when parquet/data is available.
