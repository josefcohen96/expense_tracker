---
name: ship
description: Commit, push and open a pull request for the current working tree in this repo, safely — preflight the diff for stray DB/backup/secret files, run the pinned test suite, branch off main, write a conventional commit, push, and create the PR (gh) or hand back the compare URL. Use for "/ship", "commit this", "push and open a PR", "create a PR". Flags: --main (commit straight to main), --no-pr, --no-tests, -m "message".
metadata:
  author: fable
  version: 1.0.0
---

## Arguments

`/ship [-m "<commit subject>"] [--main] [--no-pr] [--no-tests] [--draft]`

- `-m` — commit subject. Without it, derive one from the diff.
- `--main` — commit directly to `main` and push (this repo does that for small fixes). Default is a branch + PR.
- `--no-pr` — push the branch, skip the PR.
- `--no-tests` — skip the test run (only when the user says so explicitly).
- `--draft` — open the PR as a draft.

## Facts about this repo

- Remote: `origin` → `https://github.com/josefcohen96/expense_tracker`. Default branch `main`.
- Branches from Claude Code web are named `claude/<slug>-<id>`; local branches use `claude/<slug>`. Slug is short, kebab-case, English.
- Commit subjects follow conventional commits as the log does: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`; a module prefix in the subject is welcome (`Workouts: ...` appears in history too). Body in English, wrapped, explaining the *why*. Hebrew is fine inside quotes for UI labels.
- Every commit ends with the attribution line the session was given (`Co-Authored-By: Claude ...`). Every PR body ends with the generated-with line.
- `gh` is installed at `C:\Program Files\GitHub CLI\gh.exe` and authenticated as `josefcohen96` (checked 2026-09-24). It is on the machine PATH, but a session started before the install may not see it: if `gh` is not found, call it by full path (`& "C:\Program Files\GitHub CLI\gh.exe" ...` in PowerShell, `"/c/Program Files/GitHub CLI/gh.exe"` in Bash). Only fall back to "PR without gh" if the binary is gone or `gh auth status` fails.

## Step 1 — Preflight (never skip)

```
git status --porcelain
git diff --stat
git diff
```

Read the whole diff. Refuse to continue, and tell the user why, if any of these show up as added or modified:

- `*.db`, `*.sqlite3`, anything under `app/backend/data/`, `backups/`, `logs/`, `app/uploads/` (all gitignored, so their presence means someone forced them).
- `.env` or any file containing what looks like a password, token, or `SESSION_SECRET_KEY` value.
- `Mobile UX navigation improvements.zip` or other design exports.
- Untracked files the user did not ask for (scratch scripts, screenshots). Ask whether to include or delete them; do not guess.

Also check `git log origin/main..HEAD` — if there are already local commits ahead of `origin/main`, say so and include them in the push rather than creating a second branch.

## Step 2 — Tests

Run with the pinned interpreter. The global Python has the wrong Starlette and every page 500s under it.

### Test interpreter

In this order, use the first that exists:

1. `.venv/Scripts/python.exe` (project root, gitignored).
2. The scratch venv from an earlier session: `C:/Users/cohen/AppData/Local/Temp/claude/C--Users-cohen-Desktop-projects-expense-tracker/479e967f-7840-4ac0-8a49-25575b4a950b/scratchpad/venv/Scripts/python.exe`.
3. Otherwise create `.venv` (project root): `py -3.12 -m venv .venv` (or `python -m venv .venv`), then `.venv/Scripts/python.exe -m pip install -r requirements.txt`; if `watchfiles` has no wheel, install the rest without it (it is only needed for `--reload`).

```
<python> -m pytest tests -q -p no:cacheprovider
```

Known pre-existing failures on `main` (as of 2026-09-20): backup re-entry, dashboard KPI labels, three transaction-update tests. If a failure is not in that set and touches files in the diff, stop and fix it before shipping. If you are unsure whether a failure is pre-existing, run the same test on a `main` baseline via `git worktree add <scratchpad>/baseline main` (do not `git stash -u` while a dev server is running; an empty untracked data dir gets locked).

Record the result line (`N passed, M failed`) for the PR body.

## Step 3 — Branch

```
git fetch origin main
git branch --show-current
```

- If `--main`: stay on `main`; make sure it is up to date (`git pull --ff-only origin main`) before committing.
- Otherwise, if on `main`: `git checkout -b claude/<slug>` where `<slug>` comes from the commit subject (e.g. `feat: add milestone reminders` → `claude/milestone-reminders`).
- If already on a feature branch: keep it.

## Step 4 — Commit

Stage explicitly. Prefer `git add <paths>` for the files you reviewed over `git add -A`, and include the spec file under `docs/specs/` when the change came from `/feature`.

Message: subject under 72 chars in conventional-commit form, blank line, a body of two to six lines on what changed and why (not a file list), blank line, the attribution line. Write it with a here-string (PowerShell) or a heredoc (Bash) so the newlines survive:

```
git commit -F - <<'EOF'
feat: <subject>

<why this change, in two to six lines>

Co-Authored-By: <attribution from the session>
EOF
```

Then `git log -1 --stat` and read it back; amend only if the message is wrong, never to fold in files you did not review.

## Step 5 — Push

```
git push -u origin <branch>
```

For `--main`, `git push origin main`. Never force-push. If the push is rejected as non-fast-forward, fetch, rebase onto `origin/<branch>`, re-run the tests, push again.

## Step 6 — Pull request

Skip if `--no-pr` or `--main`.

PR title = commit subject (without the type prefix if it reads better). PR body:

```
## Summary
- <two to four bullets: what changed, in user terms>

## Why
<one paragraph, or the spec's "signature" line; link the spec file if there is one: docs/specs/...>

## Test plan
- [x] `pytest tests` — <N passed, M failed (pre-existing: ...)>
- [x] <browser check done, viewport, what was looked at>
- [ ] <anything left for the reviewer>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

**With gh** (once installed and authenticated):

```
gh pr create --base main --head <branch> --title "<title>" --body-file <scratchpad>/pr-body.md [--draft]
```

**PR without gh** (only if the binary is missing or unauthenticated): after the push, print the ready-to-open URL and the PR body so the user can paste it:

```
https://github.com/josefcohen96/expense_tracker/compare/main...<branch>?expand=1
```

Write the body to `<scratchpad>/pr-body.md` too and say where it is. Do not try to create the PR through the GitHub API with `curl` and a token; that needs credentials the session should not go looking for.

## Closing message

One line with the branch and the PR link or compare URL. Then the commit subject, the test result line, and anything the user must do themselves (paste the PR body, install `gh`). Nothing else.

## Never

- Commit `*.db`, backups, logs, uploads, `.env`, or design zips.
- `git push --force`, `git reset --hard`, `git checkout -- <file>` on work you did not create.
- Skip hooks or signing.
- Amend a commit that has already been pushed.
- Open a PR against anything but `main`.
