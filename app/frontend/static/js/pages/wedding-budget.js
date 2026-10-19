function openModal(id) {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    document.getElementById(id).classList.remove('hidden');
}
function closeModal(id) {
    document.getElementById(id).classList.add('hidden');
    if (id === 'add-item-modal') {
        document.getElementById('item-id').value = '';
        document.getElementById('item-modal-title').textContent = 'הוספת הוצאה ידנית';
        ['i-name','i-budgeted','i-actual','i-notes'].forEach(f => document.getElementById(f).value = '');
        document.getElementById('i-category').value = 'misc';
    }
}

function budgetFormValues() {
    const guests = parseFloat(document.getElementById('guest-count-input').value) || 0;
    const avg = parseFloat(document.getElementById('avg-per-guest-input').value) || 0;
    const addition = parseFloat(document.getElementById('our-addition-input').value) || 0;
    return {guests, avg, addition, total: guests * avg + addition};
}

function updateBudgetPreview() {
    const {total} = budgetFormValues();
    document.getElementById('budget-preview').textContent = '₪' + total.toLocaleString('en-US', {maximumFractionDigits: 0});
}

function saveTotalBudget() {
    const {guests, avg, addition, total} = budgetFormValues();
    if (guests < 0 || avg < 0 || addition < 0) { alert('יש להזין ערכים תקינים'); return; }
    const settings = [
        {key: 'budget_guest_count', value: String(guests)},
        {key: 'budget_avg_per_guest', value: String(avg)},
        {key: 'budget_our_addition', value: String(addition)},
        {key: 'total_budget', value: String(total)},
    ];
    Promise.all(settings.map(s => fetch('/api/wedding/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(s)
    }).then(r => { if (!r.ok) throw new Error(); })))
    .then(() => location.reload())
    .catch(() => alert('שגיאה בשמירה'));
}

updateBudgetPreview();

function editItem(item) {
    document.getElementById('item-modal-title').textContent = 'עריכת הוצאה';
    document.getElementById('item-id').value = item.id;
    document.getElementById('i-name').value = item.name || '';
    document.getElementById('i-category').value = item.category || 'misc';
    document.getElementById('i-budgeted').value = item.budgeted_amount || 0;
    document.getElementById('i-actual').value = item.actual_amount || 0;
    document.getElementById('i-notes').value = item.notes || '';
    openModal('add-item-modal');
}

function saveItem() {
    const id = document.getElementById('item-id').value;
    const payload = {
        name: document.getElementById('i-name').value.trim(),
        category: document.getElementById('i-category').value,
        budgeted_amount: parseFloat(document.getElementById('i-budgeted').value) || 0,
        actual_amount: parseFloat(document.getElementById('i-actual').value) || 0,
        notes: document.getElementById('i-notes').value.trim() || null,
    };
    if (!payload.name) { alert('יש להזין שם'); return; }

    const url = id ? `/api/wedding/budget-items/${id}` : '/api/wedding/budget-items';
    const method = id ? 'PUT' : 'POST';
    fetch(url, {method, headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)})
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(() => location.reload())
        .catch(() => alert('שגיאה בשמירה'));
}

function deleteItem(id) {
    if (!confirm('למחוק פריט זה?')) return;
    fetch(`/api/wedding/budget-items/${id}`, {method:'DELETE'}).then(() => location.reload());
}
