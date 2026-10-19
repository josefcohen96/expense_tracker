    const PAGE_DATA = JSON.parse(document.getElementById('journal-data').textContent);
    const TODAY = PAGE_DATA.today;
    const fileInput = document.getElementById('journal-file-input');

    // Photos chosen in the form but not uploaded yet — a brand new entry has no
    // id to upload against until it is saved.
    const pendingPhotos = { before: null, after: null };
    const existingPhotos = { before: null, after: null };
    const previewUrls = { before: null, after: null };

    function photoUrl(name) {
        return '/api/renovation/journal-photos/' + name;
    }

    /**
     * Shrink a photo before it leaves the phone: a 12MP camera file is ~5MB and
     * nothing here is shown wider than a screen. Also normalises formats the
     * server does not accept (an iPhone HEIC) into plain JPEG.
     */
    async function prepareImage(file) {
        if (!file.type.startsWith('image/') && !/\.(hei[cf])$/i.test(file.name || '')) return file;
        let bitmap;
        try {
            bitmap = await createImageBitmap(file);
        } catch (_) {
            return file;  // Let the server decide; it answers with a clear message.
        }
        const maxSide = 1600;
        const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(bitmap.width * scale);
        canvas.height = Math.round(bitmap.height * scale);
        canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        bitmap.close && bitmap.close();
        const blob = await new Promise(res => canvas.toBlob(res, 'image/jpeg', 0.85));
        if (!blob) return file;
        return new File([blob], 'photo.jpg', { type: 'image/jpeg' });
    }

    /** Open the OS picker and hand the chosen file to `onPick`. */
    function choosePhoto(onPick) {
        fileInput.value = '';
        fileInput.onchange = async () => {
            const file = fileInput.files && fileInput.files[0];
            if (file) await onPick(file);
        };
        fileInput.click();
    }

    async function uploadPhoto(entryId, slot, file) {
        const form = new FormData();
        form.append('file', await prepareImage(file));
        return renoApi(`/api/renovation/journal/${entryId}/photo/${slot}`, 'POST', form);
    }

    /** Upload straight from a card — an entry that already exists needs no form. */
    function pickJournalPhoto(entryId, slot) {
        choosePhoto(async (file) => {
            renoToast('מעלה את התמונה...');
            const result = await uploadPhoto(entryId, slot, file);
            if (result) window.location.reload();
        });
    }

    function pickModalPhoto(slot) {
        choosePhoto(async (file) => {
            pendingPhotos[slot] = file;
            renderTile(slot);
        });
    }

    async function clearModalPhoto(event, slot) {
        event.stopPropagation();
        if (pendingPhotos[slot]) {
            pendingPhotos[slot] = null;
            renderTile(slot);
            return;
        }
        const id = document.getElementById('journal-id').value;
        if (!id || !existingPhotos[slot]) return;
        if (!confirm('למחוק את התמונה?')) return;
        const result = await renoApi(`/api/renovation/journal/${id}/photo/${slot}`, 'DELETE');
        if (!result) return;
        existingPhotos[slot] = null;
        renderTile(slot);
    }

    function renderTile(slot) {
        const tile = document.getElementById('journal-tile-' + slot);
        const label = slot === 'before' ? 'לפני' : 'אחרי';

        if (previewUrls[slot]) {
            URL.revokeObjectURL(previewUrls[slot]);
            previewUrls[slot] = null;
        }

        let src = null;
        if (pendingPhotos[slot]) {
            src = previewUrls[slot] = URL.createObjectURL(pendingPhotos[slot]);
        } else if (existingPhotos[slot]) {
            src = photoUrl(existingPhotos[slot]);
        }

        tile.replaceChildren();
        if (!src) {
            tile.insertAdjacentHTML('beforeend',
                `<span class="r-upload-icon">${slot === 'before' ? '📷' : '✨'}</span>` +
                `<span>תמונת "${label}"</span>`);
            return;
        }

        const img = document.createElement('img');
        img.src = src;
        img.alt = 'תמונת ' + label;
        const caption = document.createElement('span');
        caption.className = 'r-upload-label';
        caption.textContent = label;
        const clear = document.createElement('span');
        clear.className = 'r-upload-clear';
        clear.textContent = '✕';
        clear.setAttribute('role', 'button');
        clear.setAttribute('aria-label', 'הסרת התמונה');
        clear.onclick = (e) => clearModalPhoto(e, slot);
        tile.append(img, caption, clear);
    }

    function openJournalModal(entry) {
        document.getElementById('journal-modal-title').textContent = entry ? 'עריכת תיעוד' : 'תיעוד חדש';
        document.getElementById('journal-id').value = entry ? entry.id : '';
        document.getElementById('journal-title').value = entry ? entry.title : '';
        document.getElementById('journal-date').value = entry && entry.entry_date ? entry.entry_date : TODAY;
        document.getElementById('journal-room').value = entry && entry.room_id ? String(entry.room_id) : '';
        document.getElementById('journal-notes').value = entry && entry.notes ? entry.notes : '';

        pendingPhotos.before = pendingPhotos.after = null;
        existingPhotos.before = entry ? entry.before_photo : null;
        existingPhotos.after = entry ? entry.after_photo : null;
        renderTile('before');
        renderTile('after');

        renoOpenModal('journal-modal');
        setTimeout(() => document.getElementById('journal-title').focus(), 60);
    }

    async function saveJournalEntry() {
        const id = document.getElementById('journal-id').value;
        const title = document.getElementById('journal-title').value.trim();
        if (!title) {
            renoToast('צריך לכתוב מה תיעדנו', true);
            document.getElementById('journal-title').focus();
            return;
        }
        const roomValue = document.getElementById('journal-room').value;
        const body = {
            title,
            entry_date: document.getElementById('journal-date').value || null,
            room_id: roomValue ? Number(roomValue) : null,
            notes: document.getElementById('journal-notes').value.trim() || null,
        };

        const saveBtn = document.getElementById('journal-save-btn');
        saveBtn.disabled = true;
        saveBtn.textContent = 'שומר...';
        const saved = await renoApi(
            id ? `/api/renovation/journal/${id}` : '/api/renovation/journal',
            id ? 'PUT' : 'POST',
            body,
        );

        // The entry is saved either way; a photo that fails to upload leaves the
        // rest of the entry intact and says so.
        if (saved) {
            for (const slot of ['before', 'after']) {
                if (!pendingPhotos[slot]) continue;
                saveBtn.textContent = 'מעלה תמונות...';
                await uploadPhoto(saved.id, slot, pendingPhotos[slot]);
            }
        }

        saveBtn.disabled = false;
        saveBtn.textContent = 'שמירה';
        if (!saved) return;
        renoCloseModal('journal-modal');
        window.location.reload();
    }

    async function deleteJournalEntry(id) {
        if (!confirm('למחוק את התיעוד? גם התמונות יימחקו.')) return;
        const result = await renoApi(`/api/renovation/journal/${id}`, 'DELETE');
        if (result) window.location.reload();
    }

    // Same deep link as the other pages: ?new=1 opens the form once.
    if (new URLSearchParams(window.location.search).get('new') === '1') {
        const url = new URL(window.location.href);
        url.searchParams.delete('new');
        window.history.replaceState({}, '', url);
        openJournalModal();
    }
