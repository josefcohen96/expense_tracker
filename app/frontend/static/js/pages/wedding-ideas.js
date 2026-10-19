const IDEA_BG = {
    white:  ['bg-white'],
    rose:   ['bg-rose-50'],
    orange: ['bg-orange-50'],
    yellow: ['bg-amber-50'],
    green:  ['bg-green-50'],
    teal:   ['bg-teal-50'],
    blue:   ['bg-sky-50'],
    purple: ['bg-purple-50'],
    pink:   ['bg-pink-50'],
};
const STATUS_CLASSES = {
    new:         'border-blue-300 bg-blue-50 text-blue-700',
    considering: 'border-amber-300 bg-amber-50 text-amber-700',
    approved:    'border-green-300 bg-green-50 text-green-700',
    rejected:    'border-gray-300 bg-gray-100 text-gray-500',
};

function selectIdeaColor(color) {
    document.getElementById('idea-color-input').value = color;
    document.querySelectorAll('.idea-color').forEach(s => {
        const sel = s.dataset.color === color;
        s.classList.toggle('ring-2', sel);
        s.classList.toggle('ring-rose-500', sel);
        s.classList.toggle('scale-110', sel);
    });
    const card = document.getElementById('idea-modal-card');
    Object.values(IDEA_BG).flat().forEach(c => card.classList.remove(c));
    (IDEA_BG[color] || IDEA_BG.white).forEach(c => card.classList.add(c));
}

function selectCategory(cat) {
    document.getElementById('idea-category-input').value = cat;
    document.querySelectorAll('.cat-btn').forEach(b => {
        const active = b.dataset.cat === cat;
        b.classList.toggle('bg-rose-600',     active);
        b.classList.toggle('text-white',      active);
        b.classList.toggle('border-rose-600', active);
        b.classList.toggle('bg-white',        !active);
        b.classList.toggle('text-gray-600',   !active);
        b.classList.toggle('border-gray-200', !active);
    });
}

function selectIdeaStatus(status) {
    document.getElementById('idea-status-input').value = status;
    document.querySelectorAll('.status-btn').forEach(b => {
        const active = b.dataset.status === status;
        b.className = `status-btn px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors ${
            active ? STATUS_CLASSES[status] : 'border-gray-200 bg-white text-gray-500'
        }`;
    });
}

function openIdeaModal() {
    document.getElementById('idea-id-input').value = '';
    document.getElementById('idea-title-input').value = '';
    document.getElementById('idea-desc-input').value = '';
    document.getElementById('idea-modal-title').textContent = 'רעיון חדש';
    selectIdeaColor('white');
    selectCategory('כללי');
    selectIdeaStatus('new');
    showIdeaModal();
    setTimeout(() => document.getElementById('idea-title-input').focus(), 50);
}

function openEditIdeaModal(idea) {
    document.getElementById('idea-id-input').value = idea.id;
    document.getElementById('idea-title-input').value = idea.title;
    document.getElementById('idea-desc-input').value = idea.description || '';
    document.getElementById('idea-modal-title').textContent = 'עריכת רעיון';
    selectIdeaColor(idea.color || 'white');
    selectCategory(idea.category || 'כללי');
    selectIdeaStatus(idea.status || 'new');
    showIdeaModal();
}

function showIdeaModal() {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    const modal = document.getElementById('idea-modal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeIdeaModal() {
    const modal = document.getElementById('idea-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

async function saveIdea() {
    const id    = document.getElementById('idea-id-input').value;
    const title = document.getElementById('idea-title-input').value.trim();
    if (!title) {
        document.getElementById('idea-title-input').focus();
        return;
    }
    const body = {
        title,
        description: document.getElementById('idea-desc-input').value.trim(),
        category:    document.getElementById('idea-category-input').value,
        status:      document.getElementById('idea-status-input').value,
        color:       document.getElementById('idea-color-input').value,
    };
    const url    = id ? `/api/wedding/ideas/${id}` : '/api/wedding/ideas';
    const method = id ? 'PUT' : 'POST';
    try {
        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error('http ' + res.status);
        closeIdeaModal();
        location.reload();
    } catch (e) { alert('שגיאה בשמירת הרעיון'); }
}

async function deleteIdea(id) {
    if (!confirm('למחוק את הרעיון?')) return;
    try {
        const res = await fetch(`/api/wedding/ideas/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('http ' + res.status);
        location.reload();
    } catch (e) { alert('שגיאה במחיקה'); }
}
