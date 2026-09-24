---
name: feature-design
description: Design a new feature for this app so it is distinctive to Yosef & Karina's household rather than generic tracker fare, and write it up as an implementable spec in docs/specs/. Use whenever a new feature, screen, or module is proposed, before any code — including "add X", "I want a Y page", or "what if the app could Z". Runs in the main (Fable) session; the spec it produces is what the implementer agent builds from.
metadata:
  author: fable
  version: 1.0.0
---

## Why this skill exists

The obvious version of any feature ("a page that lists X with filters") is what every app ships. This app's best parts are not obvious: the workout tracker became an arena where a station is conquered by *doing* five workouts, not by tapping "done"; the home screen is not a dashboard but היום, a queue of what needs attention today across money, wedding and training; wedding milestones are anchored to the wedding date so moving the date moves the whole plan; the tab-bar "+" knows which module you are in; mistakes get an undo pill, not a confirm dialog.

Every new feature should earn a place on that list. This skill is the thinking procedure that gets it there. Its output is a spec file, not code.

## Step 0 — Ground the request (5 minutes, no ideas yet)

Answer these in writing before proposing anything:

- **Who, exactly.** Yosef and Karina share the money and the wedding. Yonatan only trains. Tsahala only sees renovation. Which of them touches this, and on which device (almost always a phone, one-handed, in Hebrew)?
- **Which moment.** When in their day or week does this come up? Sunday-night money review, the morning glance at היום, mid-workout, at a vendor meeting? The moment sets the tone and the tap budget.
- **What already exists.** Grep for the nearest neighbour (a similar route, template, service). Read it. Most "new" features are a new angle on data the app already holds.
- **What the app already knows** that a generic app would not: the wedding date and countdown, the two payers and their colours (`services/people.py`), venue capacity vs. headcount, committed money, streaks and stations, recurring charges and their next dates. Distinctiveness usually comes from using one of these.

## Step 1 — Diverge: three framings, deliberately different

Write all three, each in three to five lines. Do not pick yet.

**A. The straight version.** What any expense or wedding app would ship. Write it honestly; it is the baseline the others must beat.

**B. The house-style version.** Ask what *this* app would do, given its personality: turn a list into a queue; turn a chore into a game with earned progress; anchor to a date or a person; make the default answer right so no tap is needed; replace a confirmation with an undo. Pick one or two of these moves and apply them.

**C. The subtraction version.** Solve it by removing, merging or changing a default rather than adding a screen. Can an existing screen absorb it? Can a setting become automatic? Can one number replace a table?

Then one extra prompt, one line each: what would a **calendar** app, a **messaging** app, a **board game** and a **bank statement** each do with this problem? Steal anything that fits.

## Step 2 — The generic detector

Score the leading candidate. It needs **at least 3 of 5** or it goes back to Step 1.

1. It names something only this household has (a wedding date, two named payers, a streak, a station, a venue, a vendor deposit).
2. It can be described without the words *manage, track, view, dashboard, settings, list*.
3. It saves a tap or a decision on a phone compared with today.
4. It has a moment of relief or delight (an undo, a countdown ticking down, a reward, a number that finally says "you're fine").
5. Yosef or Karina would notice it a week later and be glad it exists.

Also apply the **paste test**: if the description could be pasted into any other expense app's changelog without editing, it is not designed yet.

## Step 3 — Converge and name it

Choose one framing (or a merge). Write one line each on why the others lost; this goes in the spec so the reasoning survives. Then:

- **Name it in Hebrew the way Karina would say it out loud** (the app's names are short and human: היום, הזירה, אבני דרך). The label is part of the design.
- **Pick the one signature detail** — the thing you would tell a friend about. If there is none, the feature is not done.
- **Decide what is derived and what is stored.** Anything computable from existing rows is computed in a service (`services/`), never persisted.
- **Decide the mobile/desktop split.** Mobile-first in `lg:hidden` containers; desktop unchanged unless the feature is desktop.

## Step 4 — Write the spec

Create `docs/specs/YYYY-MM-DD-<slug>.md` (English file name, `docs/specs/` is committed so the design log lives with the code). Use exactly these sections so the implementer agent can rely on them:

```markdown
# <Hebrew name> — <English slug>

**Date:** YYYY-MM-DD · **Module:** finances | wedding | workouts | shell · **Who:** Yosef & Karina | Yonatan | ...

## In one line
What it does, for whom, in which moment.

## The signature
The one detail that makes it this app's, and why.

## Framings considered
- A (straight): ... — lost because ...
- B (house style): ... — chosen / lost because ...
- C (subtraction): ... — lost because ...

## Behaviour
Screen by screen, in user terms. Hebrew labels quoted verbatim. Empty states. Errors. Undo.
Mobile (< lg) and desktop (unchanged / what changes) called out separately.

## Data
Tables/columns to add (with the db-migration pattern), what is derived and where (which service), what is never stored.

## API
Routes with method, path, request/response shape, who may call them (access.py rules).

## Files to touch
Existing files, one line each on what changes. New files with their location.

## Acceptance criteria
Numbered, each testable by a pytest in tests/ or a browser check on the seeded copy.

## Tests to add
Test names and what each asserts.

## Out of scope
Explicitly not doing, so the implementer does not drift.

## Open questions
Anything the user must decide. Empty means implement as written.
```

## Step 5 — Hand back

Reply to the user with the Hebrew name, the one-line, the signature, and the three framings in one line each. Say where the spec is. If **Open questions** is non-empty, ask them now. Otherwise say the spec is ready for `/feature --go` or for the `implementer` agent.

## Things that mark a spec as not ready

- The word "dashboard" or "settings page" without a fight.
- A new column for something a `SELECT ... SUM` could give.
- A confirm dialog where an undo would do.
- A desktop change the user did not ask for.
- English strings in the UI, or Hebrew in identifiers.
- Acceptance criteria that cannot be turned into a test.
