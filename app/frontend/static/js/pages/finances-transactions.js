    // Filter panel toggle
    function toggleFilters() {
        const body = document.getElementById('filters-body');
        const chevron = document.getElementById('filter-chevron');
        const header = document.getElementById('filters-header');
        const isVisible = body.style.display !== 'none';
        if (isVisible) {
            body.style.display = 'none';
            chevron.style.transform = 'rotate(-90deg)';
            header.style.borderBottom = 'none';
        } else {
            body.style.display = 'block';
            body.style.borderTop = '1px solid #e5e7eb';
            chevron.style.transform = 'rotate(0deg)';
            header.style.borderBottom = '';
        }
    }

    // Enhanced JavaScript functionality
    let currentSort = 'date_desc';

    // Inline editing functions - defined first to ensure they're available
    window.editTransactionInline = function (id) {
        // Hide view mode elements and show edit mode elements
        const viewElements = document.querySelectorAll(`[id$="-view-${id}"]`);
        const editElements = document.querySelectorAll(`[id$="-edit-${id}"]`);

        viewElements.forEach(el => el.classList.add('hidden'));
        editElements.forEach(el => el.classList.remove('hidden'));

        // Show save/cancel buttons
        const saveBtn = document.getElementById(`save-btn-${id}`);
        const cancelBtn = document.getElementById(`cancel-btn-${id}`);

        if (saveBtn) saveBtn.classList.remove('hidden');
        if (cancelBtn) cancelBtn.classList.remove('hidden');

        // Hide edit button
        const editBtn = document.querySelector(`[onclick="editTransactionInline(${id})"]`);
        if (editBtn) editBtn.classList.add('hidden');
    }

    window.saveTransactionInline = function (id) {
        // Get all the edited values
        const date = document.getElementById(`date-edit-${id}`).value;
        const amount = parseFloat(document.getElementById(`amount-edit-${id}`).value);
        const categoryId = document.getElementById(`category-edit-${id}`).value;
        const userId = document.getElementById(`user-edit-${id}`).value;
        const accountId = document.getElementById(`account-edit-${id}`).value || null;
        const notesEl = document.getElementById(`notes-edit-${id}`);
        const tagsEl = document.getElementById(`tags-edit-${id}`);
        const notes = notesEl ? notesEl.value : null;
        const tags = tagsEl ? tagsEl.value : null;

        // Determine if it's income or expense based on original amount
        const originalAmount = parseFloat(document.getElementById(`amount-view-${id}`).textContent.replace(/[₪+\s]/g, ''));
        const isIncome = originalAmount > 0;
        const finalAmount = isIncome ? Math.abs(amount) : -Math.abs(amount);

        const transactionData = {
            date: date,
            amount: finalAmount,
            category_id: parseInt(categoryId),
            user_id: parseInt(userId),
            account_id: accountId ? parseInt(accountId) : null,
            notes: notes !== null ? (notes.trim() || null) : null,
            tags: tags !== null ? (tags.trim() || null) : null
        };

        // Show loading state
        const saveBtn = document.getElementById(`save-btn-${id}`);
        const originalText = saveBtn.innerHTML;
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        saveBtn.disabled = true;

        fetch(`/api/transactions/${id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(transactionData)
        })
            .then(response => {
                if (response.ok) {
                    return response.json();
                }
                throw new Error('Update failed');
            })
            .then(data => {
                // Update the view elements with new data
                document.getElementById(`date-view-${id}`).textContent = date;
                const serverAmount = Number((data && data.amount) ?? finalAmount);
                const amountText = `${serverAmount > 0 ? '+' : ''}₪${Math.abs(serverAmount).toFixed(2)}`;
                const amountEl = document.getElementById(`amount-view-${id}`);
                amountEl.textContent = amountText;
                amountEl.className = `font-bold text-lg ${serverAmount > 0 ? 'text-green-600' : 'text-red-600'} view-mode`;

                // Update category
                const categorySelect = document.getElementById(`category-edit-${id}`);
                const selectedCategory = categorySelect.options[categorySelect.selectedIndex].text;
                document.getElementById(`category-view-${id}`).innerHTML = `<i class="fas fa-tag mr-1"></i>${selectedCategory}`;

                // Update user
                const userSelect = document.getElementById(`user-edit-${id}`);
                const selectedUser = userSelect.options[userSelect.selectedIndex].text;
                document.getElementById(`user-view-${id}`).textContent = selectedUser;

                // Update account
                const accountSelect = document.getElementById(`account-edit-${id}`);
                const selectedAccount = accountSelect.options[accountSelect.selectedIndex].text;
                if (selectedAccount !== 'בחר חשבון (אופציונלי)') {
                    document.getElementById(`account-view-${id}`).innerHTML = `<span class="inline-flex items-center px-2 py-1 rounded text-sm bg-gray-100 text-gray-800"><i class="fas fa-credit-card mr-1"></i>${selectedAccount}</span>`;
                } else {
                    document.getElementById(`account-view-${id}`).innerHTML = '<span class="text-gray-400">-</span>';
                }

                // Update notes view
                const updatedNotes = (data && typeof data.notes !== 'undefined') ? data.notes : notes;
                const notesView = document.getElementById(`notes-view-${id}`);
                if (notesView) {
                    if (updatedNotes && updatedNotes.trim()) {
                        notesView.className = 'max-w-xs truncate view-mode';
                        notesView.innerHTML = `<i class=\"fas fa-sticky-note text-gray-400 mr-1\"></i>${updatedNotes}`;
                    } else {
                        notesView.className = 'text-gray-400 view-mode';
                        notesView.textContent = '-';
                    }
                }

                // Update tags view
                const updatedTags = (data && typeof data.tags !== 'undefined') ? data.tags : tags;
                const tagsView = document.getElementById(`tags-view-${id}`);
                if (tagsView) {
                    if (updatedTags && updatedTags.trim()) {
                        const tagHtml = updatedTags.split(',').map(t => t.trim()).filter(Boolean).map(t => `<span class=\"inline-flex items-center px-2 py-1 rounded text-xs bg-yellow-100 text-yellow-800\"><i class=\"fas fa-tag mr-1\"></i>${t}</span>`).join('');
                        tagsView.className = 'flex flex-wrap gap-1 view-mode';
                        tagsView.innerHTML = tagHtml;
                    } else {
                        tagsView.className = 'text-gray-400 view-mode';
                        tagsView.textContent = '-';
                    }
                }

                // Exit edit mode
                cancelEditInline(id);
                showToast('העסקה עודכנה בהצלחה!', 'success');
            })
            .catch(error => {
                console.error('Error:', error);
                showToast('שגיאה בעדכון העסקה', 'error');
            })
            .finally(() => {
                // Reset button state
                saveBtn.innerHTML = originalText;
                saveBtn.disabled = false;
            });
    }

    window.cancelEditInline = function (id) {
        // Show view mode elements and hide edit mode elements
        const viewElements = document.querySelectorAll(`[id$="-view-${id}"]`);
        const editElements = document.querySelectorAll(`[id$="-edit-${id}"]`);

        viewElements.forEach(el => el.classList.remove('hidden'));
        editElements.forEach(el => el.classList.add('hidden'));

        // Hide save/cancel buttons
        const saveBtn = document.getElementById(`save-btn-${id}`);
        const cancelBtn = document.getElementById(`cancel-btn-${id}`);

        if (saveBtn) saveBtn.classList.add('hidden');
        if (cancelBtn) cancelBtn.classList.add('hidden');

        // Show edit button
        const editBtn = document.querySelector(`[onclick="editTransactionInline(${id})"]`);
        if (editBtn) editBtn.classList.remove('hidden');
    }

    window.openAddModal = function () {
        showModal('addModal');
        document.getElementById('modal_date').value = new Date().toISOString().split('T')[0];
        setTimeout(() => document.getElementById('modal_amount').focus(), 300);
    }

    window.closeAddModal = function () {
        hideModal('addModal');
        document.getElementById('addTransactionForm').reset();
        document.getElementById('tagsPreview').innerHTML = '';
    }

    // Tags preview functionality
    document.getElementById('modal_tags').addEventListener('input', function (e) {
        const tags = e.target.value.split(',').map(tag => tag.trim()).filter(tag => tag);
        const preview = document.getElementById('tagsPreview');
        preview.innerHTML = '';

        tags.forEach(tag => {
            const tagElement = document.createElement('span');
            tagElement.className = 'inline-flex items-center px-2 py-1 rounded text-xs bg-blue-100 text-blue-800';
            tagElement.innerHTML = `<i class="fas fa-tag mr-1"></i>${tag}`;
            preview.appendChild(tagElement);
        });
    });

    window.editTransaction = function (id) {
        // Show loading state
        showToast('טוען פרטי העסקה...', 'info');

        // Redirect to edit page or open edit modal
        window.location.href = `/transactions/${id}/edit-inline`;
    }

    window.duplicateTransaction = function (id) {
        if (confirm('האם אתה בטוח שברצונך לשכפל עסקה זו?')) {
            fetch(`/api/transactions/${id}/duplicate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
                .then(response => {
                    if (response.ok) {
                        showToast('העסקה שוכפלה בהצלחה!', 'success');
                        setTimeout(() => window.location.reload(), 1000);
                    } else {
                        showToast('שגיאה בשכפול העסקה', 'error');
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    showToast('שגיאה בשכפול העסקה', 'error');
                });
        }
    }

    window.deleteTransaction = function (id) {
        if (confirm('האם אתה בטוח שברצונך למחוק עסקה זו? פעולה זו אינה הפיכה.')) {
            // Show loading state
            const row = document.querySelector(`[data-transaction-id="${id}"]`);
            if (row) {
                row.style.opacity = '0.5';
                row.style.pointerEvents = 'none';
            }

            fetch(`/api/transactions/${id}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
                .then(response => {
                    if (response.ok) {
                        showToast('העסקה נמחקה בהצלחה!', 'success');
                        if (row) {
                            row.style.animation = 'slideOut 0.3s ease-out';
                            setTimeout(() => row.remove(), 300);
                        } else {
                            window.location.reload();
                        }
                    } else {
                        showToast('שגיאה במחיקת העסקה', 'error');
                        if (row) {
                            row.style.opacity = '1';
                            row.style.pointerEvents = 'auto';
                        }
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    showToast('שגיאה במחיקת העסקה', 'error');
                    if (row) {
                        row.style.opacity = '1';
                        row.style.pointerEvents = 'auto';
                    }
                });
        }
    }

    window.submitTransaction = function (event) {
        event.preventDefault();

        const form = event.target;
        const submitBtn = form.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;

        // Show loading state
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>מוסיף...';
        submitBtn.disabled = true;

        const formData = new FormData(form);

        const transactionData = {
            date: formData.get('date'),
            amount: parseFloat(formData.get('amount')),
            category_id: parseInt(formData.get('category_id')),
            user_id: parseInt(formData.get('user_id')),
            account_id: formData.get('account_id') ? parseInt(formData.get('account_id')) : null,
            notes: formData.get('notes') || null,
            tags: formData.get('tags') || null
        };

        fetch('/api/transactions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(transactionData)
        })
            .then(response => {
                if (response.ok) {
                    showToast('העסקה נוספה בהצלחה!', 'success');
                    closeAddModal();
                    setTimeout(() => window.location.reload(), 1000);
                } else {
                    response.json().then(data => {
                        showToast('שגיאה בהוספת העסקה: ' + (data.detail || 'שגיאה לא ידועה'), 'error');
                    });
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showToast('שגיאה בהוספת העסקה', 'error');
            })
            .finally(() => {
                // Reset button state
                submitBtn.innerHTML = originalText;
                submitBtn.disabled = false;
            });
    }

    window.sortTransactions = function () {
        const sortBy = document.getElementById('sort_by').value;
        currentSort = sortBy;

        // Add loading state
        const tbody = document.querySelector('#transactions-table tbody');
        tbody.style.opacity = '0.5';

        // Reload with sort parameter
        const url = new URL(window.location);
        url.searchParams.set('sort', sortBy);
        // Preserve all other query parameters
        const currentParams = new URLSearchParams(window.location.search);
        currentParams.forEach((value, key) => {
            if (key !== 'sort') {
                url.searchParams.set(key, value);
            }
        });
        window.location.href = url.toString();
    }

    // New function to handle column header clicks
    window.toggleSort = function (column) {
        const url = new URL(window.location);
        const currentSort = url.searchParams.get('sort') || 'date_desc';

        // Determine new sort direction
        let newSort;
        if (currentSort.startsWith(column)) {
            // Toggle direction for same column
            newSort = currentSort.endsWith('_desc') ? `${column}_asc` : `${column}_desc`;
        } else {
            // Default to desc for new column
            newSort = `${column}_desc`;
        }

        url.searchParams.set('sort', newSort);
        window.location.href = url.toString();
    }

    // Update sort icons on page load
    document.addEventListener('DOMContentLoaded', function () {
        const currentSort = new URLSearchParams(window.location.search).get('sort') || 'date_desc';
        const [column, direction] = currentSort.split('_');

        // Reset all icons to default
        document.querySelectorAll('[id^="sort-icon-"]').forEach(icon => {
            icon.className = 'fas fa-sort mr-1 text-gray-400';
        });

        // Highlight active sort column
        const activeIcon = document.getElementById(`sort-icon-${column}`);
        if (activeIcon) {
            const iconClass = direction === 'desc' ? 'fa-sort-down' : 'fa-sort-up';
            activeIcon.className = `fas ${iconClass} mr-1 text-blue-600`;
        }

        // Update dropdown to match current sort
        const sortSelect = document.getElementById('sort_by');
        if (sortSelect) {
            sortSelect.value = currentSort;
        }
    });

    window.exportTransactions = function () {
        showToast('מייצא לאקסל...', 'info');

        const url = new URL('/api/transactions/export', window.location.origin);
        // Add current filters to export
        const currentParams = new URLSearchParams(window.location.search);
        currentParams.forEach((value, key) => {
            url.searchParams.set(key, value);
        });

        fetch(url)
            .then(response => {
                if (response.ok) {
                    return response.blob();
                }
                throw new Error('Export failed');
            })
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `transactions_${new Date().toISOString().split('T')[0]}.xlsx`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                showToast('הקובץ יוצא בהצלחה!', 'success');
            })
            .catch(error => {
                console.error('Export error:', error);
                showToast('שגיאה בייצוא הקובץ', 'error');
            });
    }

    // Initialize
    document.addEventListener('DOMContentLoaded', function () {
        // Set current sort
        const urlParams = new URLSearchParams(window.location.search);
        const sort = urlParams.get('sort');
        if (sort) {
            document.getElementById('sort_by').value = sort;
            currentSort = sort;
        }

        // Add animation to table rows
        const rows = document.querySelectorAll('#transactions-table tbody tr');
        rows.forEach((row, index) => {
            row.style.animationDelay = `${index * 0.1}s`;
        });

        // Clean empty filter values before form submission
        const filterForm = document.querySelector('form[method="GET"]');
        if (filterForm) {
            filterForm.addEventListener('submit', function (e) {
                const inputs = this.querySelectorAll('input, select');
                inputs.forEach(input => {
                    if (input.value === '' || input.value === null) {
                        input.disabled = true;
                    }
                });
            });
        }

        // Set current filter values from URL
        if (urlParams.get('category_id')) {
            document.getElementById('category_id').value = urlParams.get('category_id');
        }
        if (urlParams.get('user_id')) {
            document.getElementById('user_id').value = urlParams.get('user_id');
        }
        if (urlParams.get('account_id')) {
            document.getElementById('account_id').value = urlParams.get('account_id');
        }
        // transaction_type removed
        if (urlParams.get('date_from')) {
            document.getElementById('date_from').value = urlParams.get('date_from');
        }
        if (urlParams.get('date_to')) {
            document.getElementById('date_to').value = urlParams.get('date_to');
        }
        if (urlParams.get('amount_min')) {
            document.getElementById('amount_min').value = urlParams.get('amount_min');
        }
        if (urlParams.get('amount_max')) {
            document.getElementById('amount_max').value = urlParams.get('amount_max');
        }
        if (urlParams.get('tags')) {
            document.getElementById('tags').value = urlParams.get('tags');
        }
    });

    // Close modal when clicking outside
    document.getElementById('addModal').addEventListener('click', function (e) {
        if (e.target === this) {
            closeAddModal();
        }
    });
