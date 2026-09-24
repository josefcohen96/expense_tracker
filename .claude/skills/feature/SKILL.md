---
name: feature
description: End-to-end feature workflow for this repo — think with Fable, build with Opus. Designs the feature (feature-design), writes the spec, hands it to the Opus implementer agent, reviews the diff back in this session, verifies, then ships via /ship. Use for "/feature <idea>", "build me X", or any request that needs both design and implementation. Pass --go to skip the approval pause after the spec.
metadata:
  author: fable
  version: 1.0.0
---

## Roles

| Stage | Who | Why |
|---|---|---|
| Design, spec, review, decisions | **This session (Fable)** | Judgement, taste, knowing what the household actually needs |
| Writing and testing the code | **`implementer` agent (Opus)** | Cheap, fast, faithful execution of a settled spec |
| Commit, push, PR | **This session via `/ship`** | Git actions are outward-facing; keep them in the session the user watches |

Never hand the agent an unsettled design. Never let the agent commit.

## Arguments

`/feature <idea in any language> [--go] [--no-ship] [--spec docs/specs/<file>.md]`

- `--go` — do not pause for approval after the spec; implement immediately.
- `--no-ship` — stop after review; leave the working tree for the user.
- `--spec <path>` — skip design, implement an existing spec.

## Stage 1 — Design (Fable)

Invoke the `feature-design` skill with the idea. It produces `docs/specs/YYYY-MM-DD-<slug>.md`.

Show the user the Hebrew name, one-line, signature, and the framings in a few lines. Then:

- If the spec has **Open questions**, ask them (they change what gets built) and update the spec with the answers.
- Otherwise, unless `--go` was passed, stop and wait for approval. Approval in one feature does not carry to the next.

## Stage 2 — Implement (Opus)

Spawn one agent. Do not spawn more than one for a feature; if the spec is too big for one agent, the spec is too big — split the feature.

```
Agent(
  subagent_type: "implementer",
  description: "Implement <slug>",
  prompt: <the template below, filled in>
)
```

Prompt template (fill every placeholder; the agent starts cold and sees none of this conversation):

```
Implement the spec at docs/specs/<file>.md in this repo.

Context that is not in the spec:
- <anything decided in conversation: answers to open questions, user preferences, a file the user pointed at>
- Nearest existing example to copy: <file path> (<why it is the model>).
- Project skills that apply: <db-migration / api-endpoint / ...> — read them before touching those areas.

Constraints (also in your agent instructions, repeated because they matter):
- Desktop must stay pixel-identical unless the spec says otherwise.
- Do not commit or push.
- Run the full test suite with the pinned interpreter and add the tests listed in the spec.

When done, report exactly in the format your instructions specify: Done / Files changed / Tests / Deviations and doubts.
```

While the agent runs, do not poll. When its report arrives, read it fully before doing anything.

## Stage 3 — Review (Fable)

This is where the model split pays off. Review the diff yourself, against the spec, with the house rules in mind:

1. `git status` and `git diff` — read every hunk. Check that no `*.db`, `backups/`, `logs/` or `app/uploads/` files were touched.
2. Walk the **Acceptance criteria** one by one against the code, not against the agent's claims.
3. Apply the `feature-design` "not ready" list to the code: derived values stored in columns, confirm dialogs where an undo belongs, English in the UI, desktop changes, missing `cache_service` invalidation, non-idempotent migrations.
4. Check the agent's **Deviations and doubts** section. A deviation that changes behaviour is a decision for you or the user, not for the agent.
5. Run `/code-review` at `medium` for bug-hunting if the change is more than a couple of files.

Fixes:
- Small and mechanical: fix them here.
- More than a few lines, or the agent misunderstood something: send it back with `SendMessage` to the same agent (its context is intact) with a numbered list of exactly what to change. One round-trip is normal; three means the spec was unclear — fix the spec.

## Stage 4 — Verify in the app

If the feature has any UI, look at it. Use the `run` skill or the local-run notes in memory (pinned venv, seeded copy of the DB, Playwright at 375px; WebGL flags for the hologram). Screenshot mobile and, for desktop-touching changes, diff the desktop against a `git worktree` baseline of `main`. Do not judge a screen on Jinja output alone; that is how the first mobile pass shipped with misses.

## Stage 5 — Ship

Unless `--no-ship`: invoke `/ship`. It runs the tests again, branches, commits with a conventional message, pushes, and opens (or links) the PR, including the spec file in the same commit.

## Closing message to the user

Lead with what shipped and the PR link (or the compare URL). Then, briefly: what the signature detail is, anything the agent deviated on and how you resolved it, test counts if they changed, and anything left for the user to decide. No process narration.
