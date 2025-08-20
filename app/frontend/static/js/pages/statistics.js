import { by, readJSONScript } from '../charts/helpers.js';
import { initMonthly, updateMonthly } from '../charts/monthly.js';
import { initDonut } from '../charts/donut.js';
import { initUserBar } from '../charts/user-bar.js';

async function fetchMonthly({ categoryId, userId } = {}) {
  const qs = new URLSearchParams();
  if (categoryId) qs.set('category_id', categoryId);
  if (userId) qs.set('user_id', userId);
  const res = await fetch(`/api/stats/monthly-expenses${qs.toString() ? '?' + qs.toString() : ''}`);
  if (!res.ok) throw new Error('failed to fetch');
  return res.json();
}

window.addEventListener('DOMContentLoaded', async () => {
  // נתוני התחלה מהשרת
  const monthlyInitial = readJSONScript('monthly-data') || [];
  const catBreakdown   = readJSONScript('cat-breakdown') || [];
  const userBreakdown  = readJSONScript('user-breakdown') || [];

  // גרף חודשי
  const monthlyChart = initMonthly(by('monthlyChart').getContext('2d'), monthlyInitial);

  // דונאט קטגוריות
  const catLabels = catBreakdown.map(x => x.label);
  const catValues = catBreakdown.map(x => x.value);
  initDonut(by('categoryDonut').getContext('2d'), catLabels, catValues);

  // עמודות לפי משתמש
  const userLabels = userBreakdown.map(x => x.label);
  const userValues = userBreakdown.map(x => x.value);
  initUserBar(by('userBar').getContext('2d'), userLabels, userValues);

  // פילטרים
  by('applyFilters').addEventListener('click', async () => {
    const categoryId = by('filterCategory').value || null;
    const userId = by('filterUser').value || null;
    const data = await fetchMonthly({ categoryId, userId });
    updateMonthly(monthlyChart, data);
  });
});
