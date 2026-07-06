from datetime import date


def _get_or_create(conn, table, name, **extra):
    row = conn.execute(f"SELECT id FROM {table} WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cols = ["name"] + list(extra.keys())
    vals = [name] + list(extra.values())
    placeholders = ", ".join("?" for _ in vals)
    cur = conn.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})", vals)
    conn.commit()
    return cur.lastrowid


def test_yearly_comparison_structure(app_client):
    res = app_client.get("/api/statistics/yearly-comparison")
    assert res.status_code == 200
    body = res.json()

    current_year = date.today().year
    assert body["current_year"] == current_year
    assert body["previous_year"] == current_year - 1
    assert len(body["current"]) == 12
    assert len(body["previous"]) == 12
    for key in ("current_ytd", "previous_ytd", "previous_total", "ytd_change_pct"):
        assert key in body


def test_yearly_comparison_values(app_client, db_conn):
    user_id = _get_or_create(db_conn, "users", "Yosef")
    category_id = _get_or_create(db_conn, "categories", "בדיקת-שנתי")

    current_year = date.today().year
    previous_year = current_year - 1

    # One expense in January of each year; expenses are stored as negative amounts
    db_conn.execute(
        "INSERT INTO transactions (date, amount, category_id, user_id, notes) VALUES (?, ?, ?, ?, ?)",
        (f"{current_year}-01-15", -150.0, category_id, user_id, "yoy current"),
    )
    db_conn.execute(
        "INSERT INTO transactions (date, amount, category_id, user_id, notes) VALUES (?, ?, ?, ?, ?)",
        (f"{previous_year}-01-15", -100.0, category_id, user_id, "yoy previous"),
    )
    db_conn.commit()

    res = app_client.get("/api/statistics/yearly-comparison")
    assert res.status_code == 200
    body = res.json()

    assert body["current"][0] >= 150.0
    assert body["previous"][0] >= 100.0
    # January is always inside the year-to-date window
    assert body["current_ytd"] >= 150.0
    assert body["previous_ytd"] >= 100.0
