"""The Spanish spacing engine as pure functions: stage ladder, lapses, queue order, stats."""
from datetime import date, datetime, timedelta

from app.backend.app.services import spanish

DAY = date(2026, 1, 1)


def _review(item_id, grade, mode="recall", when=None, n=[0]):
    n[0] += 1
    when = when or datetime(2026, 1, 1, 9, 0) + timedelta(minutes=n[0])
    return {"id": n[0], "item_id": item_id, "grade": grade, "mode": mode,
            "reviewed_at": when.isoformat(), "context": "rest"}


def _at(day, minute=0):
    return datetime(day.year, day.month, day.day, 9, minute)


def test_stage_ladder_and_due_dates():
    assert spanish.INTERVALS == [0, 1, 3, 7, 14, 30, 60, 120]
    reviews = [
        _review("basics-001", 2, "intro", _at(DAY, 1)),
        _review("basics-001", 2, "recall", _at(DAY, 2)),
        _review("basics-001", 2, "recall", _at(DAY, 3)),
        _review("basics-001", 2, "recall", _at(DAY, 4)),
    ]
    state = spanish.item_states(reviews)["basics-001"]
    assert state["stage"] == 3
    assert state["due_on"] == date(2026, 1, 8)

    # An intro alone: stage 0, due now
    intro_only = spanish.item_states(reviews[:1])["basics-001"]
    assert (intro_only["stage"], intro_only["due_on"]) == (0, DAY)

    # Replay order is by reviewed_at, not list order
    shuffled = spanish.item_states(list(reversed(reviews)))["basics-001"]
    assert shuffled["stage"] == 3

    # Capped at the top of the ladder
    many = reviews + [_review("basics-001", 3, "recall", _at(DAY, 10 + i)) for i in range(6)]
    top = spanish.item_states(many)["basics-001"]
    assert top["stage"] == 7 and top["due_on"] == DAY + timedelta(days=120)


def test_lapse_resets_and_hard_holds():
    day = date(2026, 1, 8)
    base = [
        _review("basics-002", 2, "intro", _at(DAY, 1)),
        _review("basics-002", 2, "recall", _at(DAY, 2)),
        _review("basics-002", 2, "recall", _at(DAY, 3)),
        _review("basics-002", 2, "recall", _at(DAY, 4)),
    ]
    # שוב at stage 3 → stage 0, due now
    lapsed = spanish.item_states(base + [_review("basics-002", 0, "recall", _at(day, 5))])["basics-002"]
    assert (lapsed["stage"], lapsed["due_on"]) == (0, day)

    # קשה at stage 2 keeps stage 2, due in 3 days
    at_two = base[:3]
    hard = spanish.item_states(at_two + [_review("basics-002", 1, "recall", _at(day, 6))])["basics-002"]
    assert (hard["stage"], hard["due_on"]) == (2, day + timedelta(days=3))

    # קשה right after the intro still climbs to stage 1 (minimum 1)
    hard_new = spanish.item_states(base[:1] + [_review("basics-002", 1, "recall", _at(DAY, 7))])["basics-002"]
    assert (hard_new["stage"], hard_new["due_on"]) == (1, DAY + timedelta(days=1))

    # קל at stage 1 → stage 3
    at_one = base[:2]
    easy = spanish.item_states(at_one + [_review("basics-002", 3, "recall", _at(day, 8))])["basics-002"]
    assert easy["stage"] == 3 and easy["due_on"] == day + timedelta(days=7)


def test_queue_orders_due_before_new_and_caps_new():
    deck = spanish.load_deck()
    first_ids = [it["id"] for it in deck["items"]]

    # A fresh user: intro cards in deck order, at most new_cap
    fresh = spanish.build_queue(deck, [], DAY, limit=50)
    assert [c["id"] for c in fresh] == first_ids[:spanish.DEFAULT_NEW_CAP]
    assert all(c["mode"] == "intro" and c["stage"] == 0 for c in fresh)
    assert fresh[0]["theme_title"] == "בסיס ונימוס"
    assert spanish.build_queue(deck, [], DAY, limit=3, new_cap=8) == fresh[:3]

    # After 8 intros today: no new items unless new_cap=15
    intros = [_review(iid, 2, "intro", _at(DAY, i)) for i, iid in enumerate(first_ids[:8])]
    after = spanish.build_queue(deck, intros, DAY, limit=50)
    assert all(c["mode"] == "recall" for c in after)
    assert {c["id"] for c in after} == set(first_ids[:8])      # introduced today = due now
    more = spanish.build_queue(deck, intros, DAY, limit=50, new_cap=15)
    new_ones = [c for c in more if c["mode"] == "intro"]
    assert [c["id"] for c in new_ones] == first_ids[8:15]

    # Due items precede new ones; oldest due first
    later = DAY + timedelta(days=5)
    history = [
        _review("hotel-001", 2, "intro", _at(DAY, 1)),
        _review("hotel-001", 2, "recall", _at(DAY, 2)),                      # due DAY+1
        _review("hotel-002", 2, "intro", _at(DAY + timedelta(days=2), 1)),
        _review("hotel-002", 2, "recall", _at(DAY + timedelta(days=2), 2)),  # due DAY+3
    ]
    queue = spanish.build_queue(deck, history, later, limit=50)
    modes = [c["mode"] for c in queue]
    assert modes[:2] == ["recall", "recall"]
    assert [c["id"] for c in queue[:2]] == ["hotel-001", "hotel-002"]
    assert set(modes[2:]) == {"intro"}
    assert queue[2]["id"] == first_ids[0]

    # An item graded קל today is not in today's queue
    easy = [_review("basics-001", 2, "intro", _at(DAY, 1)), _review("basics-001", 3, "recall", _at(DAY, 2))]
    ids_today = [c["id"] for c in spanish.build_queue(deck, easy, DAY, limit=50, new_cap=15)]
    assert "basics-001" not in ids_today


def test_stats_in_pocket_and_streak():
    deck = spanish.load_deck()
    today = date(2026, 3, 10)
    climb = lambda iid, n, day: [_review(iid, 2, "intro", _at(day, 0))] + [
        _review(iid, 2, "recall", _at(day, i + 1)) for i in range(n)
    ]
    reviews = (
        climb("basics-001", 3, today - timedelta(days=2))     # stage 3 → in pocket
        + climb("basics-002", 5, today - timedelta(days=1))   # stage 5 → in pocket
        + climb("basics-003", 2, today)                       # stage 2 → learning
        + climb("basics-004", 1, today)                       # stage 1 → learning
        + climb("basics-005", 0, today)                       # stage 0 → neither
        + climb("basics-006", 6, today - timedelta(days=2))   # stage 6 → in pocket + mastered
    )
    st = spanish.stats(deck, reviews, today)
    assert st["in_pocket"] == 3
    assert st["learning"] == 2
    assert st["mastered"] == 1
    assert st["per_theme"]["basics"] == {"total": 25, "in_pocket": 3}
    assert st["per_theme"]["work"] == {"total": 25, "in_pocket": 0}
    assert st["total"] == 300
    assert st["new_today_left"] == spanish.DEFAULT_NEW_CAP - 3   # three intros today
    assert st["due_today"] == 1                                    # basics-005, stage 0

    # Streak: consecutive review days ending today (or yesterday)
    assert st["review_days_streak"] == 3
    days = {today - timedelta(days=d) for d in (1, 2, 3, 5)}
    assert spanish.review_days_streak(days, today) == 3            # ends yesterday
    assert spanish.review_days_streak(days | {today}, today) == 4
    assert spanish.review_days_streak({today - timedelta(days=2)}, today) == 0
    assert spanish.review_days_streak(set(), today) == 0
