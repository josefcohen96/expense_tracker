"""The Spanish deck is content that the reviews table references by id: its shape is a contract."""

import json
import re
from pathlib import Path

DECK_PATH = Path(__file__).resolve().parents[1] / "app" / "frontend" / "static" / "spanish" / "deck.json"

THEME_ORDER = [
    "basics", "numbers_time", "restaurant", "getting_around", "hotel", "shopping_money",
    "small_talk", "couple", "health_emergency", "daily_life", "work", "wedding_family",
]


def test_deck_shape_and_targets():
    deck = json.loads(DECK_PATH.read_text(encoding="utf-8"))
    assert deck["version"] == 1

    themes = sorted(deck["themes"], key=lambda t: t["order"])
    assert [t["key"] for t in themes] == THEME_ORDER
    assert [t["key"] for t in deck["themes"]] == THEME_ORDER
    assert all(t["title"].strip() for t in themes)

    items = deck["items"]
    assert len(items) == 300
    ids = [it["id"] for it in items]
    assert len(set(ids)) == 300

    per_theme = {key: 0 for key in THEME_ORDER}
    for it in items:
        assert it["theme"] in per_theme, it["id"]
        per_theme[it["theme"]] += 1
        assert re.fullmatch(rf"{re.escape(it['theme'])}-\d{{3}}", it["id"]), it["id"]
        for field in ("es", "he", "target_es", "target_he", "lemma"):
            assert isinstance(it[field], str) and it[field].strip(), (it["id"], field)
        assert isinstance(it.get("note", ""), str)
        assert it["target_es"] in it["es"], it["id"]
        assert "vosotros" not in it["es"].lower(), it["id"]
        words = len(it["es"].split())
        assert 3 <= words <= 9, (it["id"], words)
    assert all(count == 25 for count in per_theme.values()), per_theme

    # Ids inside a theme are numbered 001..025 in order.
    for key in THEME_ORDER:
        numbers = [int(i.rsplit("-", 1)[1]) for i in ids if i.rsplit("-", 1)[0] == key]
        assert numbers == list(range(1, 26)), key


def test_deck_words_recur_across_sentences():
    """Principle 1: a target word is met in context more than once, and the deck is not tiny."""
    deck = json.loads(DECK_PATH.read_text(encoding="utf-8"))
    items = deck["items"]
    token_sets = [set(re.findall(r"[a-záéíóúñü]+", it["es"].lower())) for it in items]
    assert len(set().union(*token_sets)) >= 450

    lemma_counts = {}
    for it in items:
        lemma_counts[it["lemma"]] = lemma_counts.get(it["lemma"], 0) + 1
    assert max(lemma_counts.values()) <= 3

    recurring = 0
    for n, it in enumerate(items):
        stems = [w[:4] for w in re.findall(r"[a-záéíóúñü]+", it["target_es"].lower())]
        seen_elsewhere = any(
            m != n and any(tok.startswith(stem) for stem in stems for tok in toks)
            for m, toks in enumerate(token_sets)
        )
        if seen_elsewhere or lemma_counts[it["lemma"]] > 1:
            recurring += 1
    assert recurring >= 200, recurring
