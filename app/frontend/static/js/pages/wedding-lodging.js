// ─── Room Modal ──────────────────────────────────────────────────────────────

function openAddRoomModal() {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    document.getElementById('room-modal-title').textContent = 'הוספת חדר';
    document.getElementById('room-id').value = '';
    document.getElementById('r-name').value = '';
    document.getElementById('r-type').value = '';
    document.getElementById('r-capacity').value = '2';
    document.getElementById('r-notes').value = '';
    document.getElementById('room-delete-btn').classList.add('hidden');
    document.getElementById('room-modal').classList.remove('hidden');
    setTimeout(function() { document.getElementById('r-name').focus(); }, 50);
}

function openEditRoomFromBtn(btn) {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    document.getElementById('room-modal-title').textContent = 'עריכת חדר';
    document.getElementById('room-id').value      = btn.dataset.roomId;
    document.getElementById('r-name').value       = btn.dataset.roomName;
    document.getElementById('r-type').value       = btn.dataset.roomType;
    document.getElementById('r-capacity').value   = btn.dataset.roomCapacity;
    document.getElementById('r-notes').value      = btn.dataset.roomNotes;
    document.getElementById('room-delete-btn').classList.remove('hidden');
    document.getElementById('room-modal').classList.remove('hidden');
}

function closeRoomModal() {
    document.getElementById('room-modal').classList.add('hidden');
}

function saveRoom() {
    var id       = document.getElementById('room-id').value;
    var name     = document.getElementById('r-name').value.trim();
    var type     = document.getElementById('r-type').value.trim() || 'יחידים';
    var capacity = parseInt(document.getElementById('r-capacity').value, 10);
    var notes    = document.getElementById('r-notes').value.trim() || null;

    if (!name) { alert('יש להזין שם חדר'); return; }
    if (!Number.isFinite(capacity) || capacity < 1) { alert('תפוסה חייבת להיות לפחות 1'); return; }

    var url    = id ? '/api/wedding/rooms/' + id : '/api/wedding/rooms';
    var method = id ? 'PUT' : 'POST';

    fetch(url, {
        method: method,
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: name, room_type: type, max_capacity: capacity, notes: notes})
    })
    .then(async function(r) {
        if (!r.ok) {
            var detail = 'HTTP ' + r.status;
            try { var data = await r.json(); if (data && data.detail) detail = data.detail; } catch (e) {}
            throw new Error(detail);
        }
        return r.json();
    })
    .then(function() { closeRoomModal(); location.reload(); })
    .catch(function(e) { alert('שגיאה בשמירה: ' + e.message); });
}

// Escape key closes the modal
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && !document.getElementById('room-modal').classList.contains('hidden')) {
        closeRoomModal();
    }
});

function deleteRoom() {
    var id = document.getElementById('room-id').value;
    if (!id) return;
    if (!confirm('למחוק את החדר? כל השיבוצים לחדר זה יוסרו.')) return;

    fetch('/api/wedding/rooms/' + id, {method: 'DELETE'})
    .then(function(r) {
        if (!r.ok) throw new Error(r.status);
        closeRoomModal();
        location.reload();
    })
    .catch(function(e) { alert('שגיאה במחיקה: ' + e.message); });
}

// ─── Guest Assignment ────────────────────────────────────────────────────────

// Called from the top "waiting" panel (guest picks a room)
function assignGuestFromTop(guestId, selectEl) {
    var roomId = selectEl.value;
    if (!roomId) return;
    selectEl.disabled = true;
    doAssign(guestId, roomId, function() {
        selectEl.disabled = false;
        selectEl.value = '';
    });
}

// Called from per-room dropdown (room picks a guest)
function assignGuestFromRoom(selectEl, roomId) {
    var guestId = parseInt(selectEl.value);
    if (!guestId) return;
    selectEl.disabled = true;
    doAssign(guestId, roomId, function() {
        selectEl.disabled = false;
        selectEl.value = '';
    });
}

function doAssign(guestId, roomId, onError) {
    fetch('/api/wedding/rooms/' + roomId + '/assign/' + guestId, {method: 'POST'})
    .then(async function(r) {
        if (!r.ok) {
            // Try to extract server-provided detail text for clearer messages
            var detail = 'HTTP ' + r.status;
            try { var data = await r.json(); if (data && data.detail) detail = data.detail; } catch (e) {}
            throw new Error(detail);
        }
        location.reload();
    })
    .catch(function(e) {
        alert('שגיאה בשיבוץ: ' + e.message);
        if (onError) onError();
    });
}

function unassignGuest(guestId) {
    if (!confirm('להסיר את האורח מהחדר?')) return;
    fetch('/api/wedding/rooms/assignments/' + guestId, {method: 'DELETE'})
    .then(function(r) {
        if (!r.ok) throw new Error(r.status);
        location.reload();
    })
    .catch(function(e) { alert('שגיאה בהסרה: ' + e.message); });
}
