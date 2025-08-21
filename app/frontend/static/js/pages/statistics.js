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
  const catBreakdown   = readJSONScript('category-data') || [];
  const userBreakdown  = readJSONScript('user-data') || [];
  const recurringUserBreakdown = readJSONScript('recurring-user-data') || [];

  // גרף חודשי
  const monthlyChart = initMonthly(by('monthly-chart').getContext('2d'), monthlyInitial);

  // דונאט קטגוריות
  const catLabels = catBreakdown.map(x => x.category);
  const catValues = catBreakdown.map(x => x.total);
  initDonut(by('donut-chart').getContext('2d'), catLabels, catValues);

  // עמודות הוצאות קבועות לפי חודש
  const recurringMonthLabels = recurringUserBreakdown.map(x => x.month);
  const recurringMonthValues = recurringUserBreakdown.map(x => x.total);
  console.log('recurringMonthLabels:', recurringMonthLabels);
  console.log('recurringMonthValues:', recurringMonthValues);
  initUserBar(by('user-bar-chart').getContext('2d'), recurringMonthLabels, recurringMonthValues);

  // פילטרים
  by('applyFilters').addEventListener('click', async () => {
    const categoryId = by('filterCategory').value || null;
    const userId = by('filterUser').value || null;
    const data = await fetchMonthly({ categoryId, userId });
    updateMonthly(monthlyChart, data);
  });
});
