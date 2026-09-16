"""Mobile סקירה (/finances) and מגמות (/finances/statistics) blocks.

Data lives in far-future months so the real rows in the copied DB don't interfere.
"""
import re
from datetime import date

import pytest

NOTE = "fx-mobile-test"
SEL = "2031-03"
PREV = "2031-02"


def _category_id(conn, name, created, is_saving=0):
    row = conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO categories (name, is_saving) VALUES (?, ?)", (name, is_saving))
    created.append(cur.lastrowid)
    return cur.lastrowid


@pytest.fixture()
def mobile_data(db_conn):
    created_categories = []
    yosef = db_conn.execute("SELECT id FROM users WHERE name = 'Yosef'").fetchone()
    karina = db_conn.execute("SELECT id FROM users WHERE name = 'Karina'").fetchone()
    assert yosef and karina
    salary = _category_id(db_conn, "משכורת", created_categories)
    home = _category_id(db_conn, "הוצאות בית", created_categories)
    car = _category_id(db_conn, "רכב", created_categories)
    fun = _category_id(db_conn, "פנאי", created_categories)
    wedding = _category_id(db_conn, "חתונה", created_categories)
    saving_row = db_conn.execute("SELECT id FROM categories WHERE is_saving = 1 ORDER BY id LIMIT 1").fetchone()
    saving = saving_row["id"] if saving_row else _category_id(db_conn, "חסכונות", created_categories, is_saving=1)

    rows = [
        # previous month: expenses 2,000 · income 10,000 · savings 1,000
        (f"{PREV}-05", -2000, home, yosef["id"], "prev home"),
        (f"{PREV}-01", 10000, salary, yosef["id"], "prev salary"),
        (f"{PREV}-02", -1000, saving, yosef["id"], "prev saving"),
        # selected month: expenses 4,600 · income 10,000 · savings 1,000
        (f"{SEL}-03", -1000, saving, yosef["id"], "saving"),
        (f"{SEL}-04", -100, fun, karina["id"], "cinema"),
        (f"{SEL}-05", -3000, home, yosef["id"], "arnona"),
        (f"{SEL}-06", -1000, wedding, karina["id"], "photographer"),
        (f"{SEL}-07", -500, car, karina["id"], ""),
        (f"{SEL}-20", 10000, salary, yosef["id"], "salary"),
    ]
    for day, amount, cat, user, note in rows:
        db_conn.execute(
            "INSERT INTO transactions (date, amount, category_id, user_id, notes, tags) VALUES (?, ?, ?, ?, ?, ?)",
            (day, amount, cat, user, note, NOTE),
        )
    db_conn.commit()
    try:
        yield
    finally:
        db_conn.execute("DELETE FROM transactions WHERE tags = ?", (NOTE,))
        for cat_id in created_categories:
            db_conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        db_conn.commit()


def _section(html, start_marker, end_marker):
    start = html.index(start_marker)
    return html[start:html.index(end_marker, start)]


def test_overview_mobile_blocks(app_client, mobile_data):
    r = app_client.get(f"/finances?month={SEL}")
    assert r.status_code == 200
    html = r.text

    # Month chips: the current month is always there; an out-of-range selection is added as active
    today = date.today()
    from app.backend.app.services.hebrew_dates import HEBREW_MONTHS
    assert f'>{HEBREW_MONTHS[today.month - 1]}</a>' in html
    assert re.search(r'class="fx-chip is-active"[^>]*>מרץ 2031</a>', html)
    assert 'type="month" class="fx-month-input" value="2031-03"' in html

    # Balance card: 10,000 − 4,600; bar = 46% expenses + 10% savings
    assert "נותר החודש" in html
    assert "₪5,400" in html
    assert "width:46.0%;background:#dc2626" in html
    assert "width:10.0%;background:#0d9488" in html
    assert "▲ 130.0%" in html      # expenses up (red)
    assert re.search(r'class="fx-delta" style="color:#9ca3af">קבוע<', html)  # savings unchanged

    # Top 3 expense categories, savings/income excluded, wedding always rose
    where = _section(html, "לאן הלך הכסף", "</section>")
    assert f'href="/finances/statistics?month={SEL}"' in where
    names = re.findall(r'class="fx-cat-name">([^<]+)<', where)
    assert names == ["הוצאות בית", "חתונה", "רכב"]
    assert "background:#e11d48" in where
    assert "width:65.2%;background:#2563eb" in where  # 3,000 / 4,600
    assert "background:#7c3aed" in where               # second non-wedding category

    # Recent rows: notes (fallback category) + meta + signed amounts
    recent = _section(html, '<ul class="fx-list">', "</ul>")
    assert "salary" in recent and "+₪10,000" in recent
    assert "משכורת · יוסף · 20.3" in recent
    assert re.search(r'class="fx-row-name">רכב<', recent)  # empty note falls back to category
    assert "₪3,000" in recent
    assert "אין עסקאות החודש" not in html

    # Desktop blocks are still rendered (hidden below lg only)
    assert "עסקאות אחרונות" in html
    assert "קטגוריות עיקריות" in html
    assert "חיובים קבועים צפויים" in html


def test_overview_mobile_empty_month(app_client):
    r = app_client.get("/finances?month=2032-07")
    assert r.status_code == 200
    assert "אין עסקאות החודש" in r.text
    assert "לאן הלך הכסף" not in r.text
    assert 'class="fx-stack"' not in r.text


def test_statistics_mobile_trends(app_client, mobile_data):
    r = app_client.get(f"/finances/statistics?month={SEL}")
    assert r.status_code == 200
    html = r.text

    assert "מרץ 2031" in html
    # Average over the months in the window that have data: (2,000 + 4,600) / 2
    assert "הוצאה חודשית ממוצעת" in html
    assert "₪3,300" in html
    assert "▲ 39.4%" in html

    chart = _section(html, '<div class="fx-chart">', '<section class="fx-biggest">')
    hrefs = re.findall(r'href="/finances/statistics\?month=(\d{4}-\d{2})"', chart)
    assert hrefs == ["2030-10", "2030-11", "2030-12", "2031-01", "2031-02", "2031-03"]
    assert chart.count("fx-bar is-zero") == 4
    assert 'class="fx-tip" dir="ltr">₪4,600<' in chart
    assert "height:100.0%;background:#2563eb" in chart   # selected month is the peak
    assert "height:43.5%;background:#dbeafe" in chart    # 2,000 / 4,600

    biggest = _section(html, "הגדול ביותר החודש", "</section>")
    names = re.findall(r'class="fx-row-name">([^<]+)<', biggest)
    assert names == ["הוצאות בית", "חתונה", "רכב"]
    assert "🏠" in biggest and "💍" in biggest and "🚗" in biggest
    assert "▲ 50%" in biggest          # הוצאות בית: 2,000 → 3,000
    assert "עסקה אחת" in biggest

    # Existing page content is still there for desktop
    assert 'id="monthly-chart"' in html
    assert 'class="fx-charts"' in html


def test_statistics_mobile_empty_window(app_client):
    r = app_client.get("/finances/statistics?month=2033-05")
    assert r.status_code == 200
    assert "מאי 2033" in r.text
    assert "הוצאה חודשית ממוצעת" not in r.text
    assert '<div class="fx-chart">' not in r.text
    assert "הגדול ביותר החודש" not in r.text
