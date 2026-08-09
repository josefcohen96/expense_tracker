"""End-to-end tests for the home renovation module: pages, CRUD, and the
per-user access rules that keep the module limited to Yosef and Tsahala.
"""
import pytest

from app.backend.app.services.access import (
    can_access_path,
    can_access_renovation,
    can_edit_renovation,
    home_path_for,
)


# ─── Access rules (pure functions, no HTTP) ─────────────────────────────────

@pytest.mark.parametrize("user, path, allowed", [
    ("YOSEF", "/renovation", True),
    ("YOSEF", "/api/renovation/tasks", True),
    ("YOSEF", "/finances", True),
    ("TSAHALA", "/renovation", True),
    ("TSAHALA", "/renovation/tasks", True),
    ("TSAHALA", "/api/renovation/rooms", True),
    ("TSAHALA", "/finances", False),
    ("TSAHALA", "/wedding/guests", False),
    ("TSAHALA", "/workouts", False),
    ("TSAHALA", "/api/wedding/guests", False),
    ("TSAHALA", "/logout", True),
    ("TSAHALA", "/static/css/renovation.css", True),
    ("KARINA", "/renovation", False),
    ("KARINA", "/api/renovation/tasks", False),
    ("KARINA", "/finances", True),
    ("KARINA", "/wedding", True),
])
def test_path_access_matrix(user, path, allowed):
    assert can_access_path({"username": user}, path) is allowed


def test_lowercase_usernames_are_matched():
    assert can_access_renovation("tsahala") is True
    assert can_access_renovation({"username": "karina"}) is False


def test_only_renovation_users_can_edit():
    assert can_edit_renovation("YOSEF") is True
    assert can_edit_renovation("TSAHALA") is True
    assert can_edit_renovation("KARINA") is False
    assert can_edit_renovation(None) is False


def test_home_path_depends_on_user():
    assert home_path_for({"username": "TSAHALA"}) == "/renovation"
    assert home_path_for({"username": "YOSEF"}) == "/finances"
    assert home_path_for(None) == "/finances"


# ─── Pages ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/renovation",
    "/renovation/tasks",
    "/renovation/ideas",
    "/renovation/rooms",
    "/renovation/supplies",
])
def test_pages_load(app_client, path):
    res = app_client.get(path)
    assert res.status_code == 200
    assert "שיפוץ הבית" in res.text


def test_rooms_are_seeded(app_client):
    rooms = app_client.get("/api/renovation/rooms").json()
    assert len(rooms) >= 1
    assert any(r["name"] == "מטבח" for r in rooms)


def test_general_room_is_replaced_by_a_real_room(app_client):
    names = [r["name"] for r in app_client.get("/api/renovation/rooms").json()]
    assert "כללי" not in names
    assert "מסדרון" in names


# ─── Task CRUD ───────────────────────────────────────────────────────────────

def test_task_lifecycle(app_client):
    room_id = app_client.get("/api/renovation/rooms").json()[0]["id"]

    created = app_client.post("/api/renovation/tasks", json={
        "title": "לצבוע את הסלון",
        "room_id": room_id,
        "priority": "high",
        "due_date": "2026-09-01",
        "notes": "  שני מעילים  ",
    })
    assert created.status_code == 201
    task = created.json()
    assert task["title"] == "לצבוע את הסלון"
    assert task["status"] == "todo"
    assert task["notes"] == "שני מעילים"  # trimmed

    updated = app_client.put(f"/api/renovation/tasks/{task['id']}", json={"status": "done"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "done"

    listed = app_client.get("/api/renovation/tasks").json()
    assert any(t["id"] == task["id"] and t["room_name"] for t in listed)

    assert app_client.delete(f"/api/renovation/tasks/{task['id']}").status_code == 204
    assert all(t["id"] != task["id"] for t in app_client.get("/api/renovation/tasks").json())


def test_task_rejects_bad_input(app_client):
    assert app_client.post("/api/renovation/tasks", json={"title": "   "}).status_code == 422
    assert app_client.post("/api/renovation/tasks", json={"title": "x", "status": "nope"}).status_code == 422
    assert app_client.post("/api/renovation/tasks", json={"title": "x", "priority": "urgent"}).status_code == 422
    assert app_client.post("/api/renovation/tasks", json={"title": "x", "room_id": 999999}).status_code == 400


def test_update_missing_task_is_404(app_client):
    assert app_client.put("/api/renovation/tasks/999999", json={"status": "done"}).status_code == 404


def test_tasks_page_filters_by_status_and_room(app_client):
    room_id = app_client.get("/api/renovation/rooms").json()[0]["id"]
    open_task = app_client.post("/api/renovation/tasks", json={
        "title": "משימה פתוחה לבדיקה", "room_id": room_id,
    }).json()
    done_task = app_client.post("/api/renovation/tasks", json={
        "title": "משימה שהושלמה לבדיקה", "room_id": room_id, "status": "done",
    }).json()

    open_page = app_client.get("/renovation/tasks?status=open").text
    assert "משימה פתוחה לבדיקה" in open_page
    assert "משימה שהושלמה לבדיקה" not in open_page

    done_page = app_client.get("/renovation/tasks?status=done").text
    assert "משימה שהושלמה לבדיקה" in done_page

    # A room with no matching tasks shows the empty state, not everything.
    other_rooms = [r for r in app_client.get("/api/renovation/rooms").json() if r["id"] != room_id]
    if other_rooms:
        other = app_client.get(f"/renovation/tasks?room={other_rooms[-1]['id']}").text
        assert "משימה פתוחה לבדיקה" not in other

    # A bad room filter must not blow up the page.
    assert app_client.get("/renovation/tasks?room=not-a-number").status_code == 200

    app_client.delete(f"/api/renovation/tasks/{open_task['id']}")
    app_client.delete(f"/api/renovation/tasks/{done_task['id']}")


# ─── Idea CRUD ───────────────────────────────────────────────────────────────

def test_idea_lifecycle(app_client):
    created = app_client.post("/api/renovation/ideas", json={
        "title": "תאורה חמה",
        "description": "ספוטים 3000K",
        "status": "considering",
        "color": "teal",
        "image_url": "https://example.com/lamp.jpg",
    })
    assert created.status_code == 201
    idea = created.json()
    assert idea["color"] == "teal"

    page = app_client.get("/renovation/ideas?status=considering").text
    assert "תאורה חמה" in page

    assert app_client.put(f"/api/renovation/ideas/{idea['id']}", json={"status": "approved"}).json()["status"] == "approved"
    assert app_client.delete(f"/api/renovation/ideas/{idea['id']}").status_code == 204


def test_idea_rejects_unknown_color(app_client):
    assert app_client.post("/api/renovation/ideas", json={"title": "x", "color": "neon"}).status_code == 422


# ─── Rooms ───────────────────────────────────────────────────────────────────

def test_deleting_a_room_keeps_its_tasks(app_client):
    room = app_client.post("/api/renovation/rooms", json={"name": "מחסן", "icon": "📦"}).json()
    task = app_client.post("/api/renovation/tasks", json={
        "title": "לסדר את המחסן", "room_id": room["id"],
    }).json()

    assert app_client.delete(f"/api/renovation/rooms/{room['id']}").status_code == 204

    survivors = app_client.get("/api/renovation/tasks").json()
    kept = next(t for t in survivors if t["id"] == task["id"])
    assert kept["room_id"] is None

    app_client.delete(f"/api/renovation/tasks/{task['id']}")


def test_room_name_cannot_be_blanked(app_client):
    room = app_client.post("/api/renovation/rooms", json={"name": "חדר זמני"}).json()
    assert app_client.put(f"/api/renovation/rooms/{room['id']}", json={"name": "  "}).status_code == 422
    app_client.delete(f"/api/renovation/rooms/{room['id']}")


# ─── Supplies (ציוד) ─────────────────────────────────────────────────────────

def test_supply_lifecycle_and_missing_view(app_client):
    room = app_client.post("/api/renovation/rooms", json={"name": "חדר ציוד"}).json()

    # Names are deliberately unlike the form's placeholder copy, so a match in
    # the page really means the item was rendered.
    missing = app_client.post("/api/renovation/supplies", json={
        "name": "פריטחסרלבדיקה", "quantity": "2 פחים", "room_id": room["id"],
    })
    assert missing.status_code == 201
    item = missing.json()
    assert item["status"] == "needed"

    bought = app_client.post("/api/renovation/supplies", json={
        "name": "פריטשנקנהלבדיקה", "room_id": room["id"], "status": "bought",
    }).json()

    # The default view is the shopping list: missing items only.
    page = app_client.get("/renovation/supplies").text
    assert "פריטחסרלבדיקה" in page
    assert "פריטשנקנהלבדיקה" not in page

    assert "פריטשנקנהלבדיקה" in app_client.get("/renovation/supplies?status=all").text
    assert "פריטחסרלבדיקה" not in app_client.get("/renovation/supplies?status=bought").text

    # Marking it bought takes it off the missing list.
    assert app_client.put(f"/api/renovation/supplies/{item['id']}", json={"status": "bought"}).status_code == 200
    assert "פריטחסרלבדיקה" not in app_client.get("/renovation/supplies").text

    for supply_id in (item["id"], bought["id"]):
        assert app_client.delete(f"/api/renovation/supplies/{supply_id}").status_code == 204
    app_client.delete(f"/api/renovation/rooms/{room['id']}")


def test_supply_added_to_a_task_inherits_its_room(app_client):
    room = app_client.post("/api/renovation/rooms", json={"name": "חדר ירושה"}).json()
    task = app_client.post("/api/renovation/tasks", json={
        "title": "להתקין מדפים", "room_id": room["id"],
    }).json()

    item = app_client.post("/api/renovation/supplies", json={
        "name": "ברגים", "task_id": task["id"],
    }).json()
    assert item["room_id"] == room["id"]

    # The task page lists the equipment it needs.
    page = app_client.get("/renovation/tasks").text
    assert "ברגים" in page

    app_client.delete(f"/api/renovation/supplies/{item['id']}")
    app_client.delete(f"/api/renovation/tasks/{task['id']}")
    app_client.delete(f"/api/renovation/rooms/{room['id']}")


def test_room_filter_chips_show_counts(app_client):
    room = app_client.post("/api/renovation/rooms", json={"name": "חדרספירה"}).json()
    open_task = app_client.post("/api/renovation/tasks", json={
        "title": "משימה פתוחה לספירה", "room_id": room["id"],
    }).json()
    done_task = app_client.post("/api/renovation/tasks", json={
        "title": "משימה סגורה לספירה", "room_id": room["id"], "status": "done",
    }).json()

    def chip_count(page: str, room_name: str) -> int:
        """Read the count rendered inside a room's filter chip."""
        import re
        match = re.search(
            room_name + r"\s*<span class=\"r-chip-count\">(\d+)</span>", page
        )
        assert match, f"no count chip found for {room_name}"
        return int(match.group(1))

    # Unfiltered: both tasks.
    assert chip_count(app_client.get("/renovation/tasks").text, "חדרספירה") == 2
    # The count follows the status filter, so it always matches what a tap shows.
    assert chip_count(app_client.get("/renovation/tasks?status=open").text, "חדרספירה") == 1
    assert chip_count(app_client.get("/renovation/tasks?status=done").text, "חדרספירה") == 1

    # Supplies and ideas count their own kind of row.
    supply = app_client.post("/api/renovation/supplies", json={
        "name": "פריטלספירה", "room_id": room["id"],
    }).json()
    assert chip_count(app_client.get("/renovation/supplies").text, "חדרספירה") == 1
    assert chip_count(app_client.get("/renovation/ideas").text, "חדרספירה") == 0

    app_client.delete(f"/api/renovation/supplies/{supply['id']}")
    for task_id in (open_task["id"], done_task["id"]):
        app_client.delete(f"/api/renovation/tasks/{task_id}")
    app_client.delete(f"/api/renovation/rooms/{room['id']}")


def test_supply_rejects_bad_input(app_client):
    assert app_client.post("/api/renovation/supplies", json={"name": "  "}).status_code == 422
    assert app_client.post("/api/renovation/supplies", json={"name": "x", "status": "maybe"}).status_code == 422
    assert app_client.post("/api/renovation/supplies", json={"name": "x", "room_id": 999999}).status_code == 400
    assert app_client.post("/api/renovation/supplies", json={"name": "x", "task_id": 999999}).status_code == 400
    assert app_client.put("/api/renovation/supplies/999999", json={"status": "bought"}).status_code == 404


def test_supplies_survive_their_task_and_room(app_client):
    room = app_client.post("/api/renovation/rooms", json={"name": "חדר חולף"}).json()
    task = app_client.post("/api/renovation/tasks", json={
        "title": "משימה חולפת", "room_id": room["id"],
    }).json()
    item = app_client.post("/api/renovation/supplies", json={
        "name": "דבק", "task_id": task["id"],
    }).json()

    app_client.delete(f"/api/renovation/tasks/{task['id']}")
    app_client.delete(f"/api/renovation/rooms/{room['id']}")

    survivors = app_client.get("/api/renovation/supplies").json()
    kept = next(s for s in survivors if s["id"] == item["id"])
    assert kept["task_id"] is None
    assert kept["room_id"] is None

    app_client.delete(f"/api/renovation/supplies/{item['id']}")


def test_renovation_users_only_may_edit_supplies():
    from app.backend.app.services.access import can_access_path
    assert can_access_path({"username": "KARINA"}, "/api/renovation/supplies") is False
    assert can_access_path({"username": "TSAHALA"}, "/renovation/supplies") is True


# ─── Dashboard aggregation ───────────────────────────────────────────────────

def test_dashboard_counts_progress(app_client):
    room = app_client.post("/api/renovation/rooms", json={"name": "חדר בדיקות"}).json()
    ids = [
        app_client.post("/api/renovation/tasks", json={
            "title": f"בדיקה {i}", "room_id": room["id"], "status": status,
        }).json()["id"]
        for i, status in enumerate(["todo", "done"])
    ]

    page = app_client.get("/renovation").text
    assert "מתקדמים" in page or "מתחילים" in page
    assert "חדר בדיקות" in page

    for task_id in ids:
        app_client.delete(f"/api/renovation/tasks/{task_id}")
    app_client.delete(f"/api/renovation/rooms/{room['id']}")
