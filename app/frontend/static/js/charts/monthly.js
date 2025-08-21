import { by, readJSONScript, labels, values, baseOptions } from "./helpers.js";

// monthly-data should be an array of objects like:
// { ym: '2025-03', expenses: 6258.31, category: 'Food' }
// If not, update backend to provide category per month.

// const data = readJSONScript("monthly-data");

function getLast6Months(data, category = "total") {
  let filtered;
  if (category === "total") {
    // Aggregate all categories per month
    const monthMap = {};
    (Array.isArray(data) ? data : []).forEach(item => {
      if (item && typeof item.ym === "string") {  
        monthMap[item.ym] = (monthMap[item.ym] || 0) + Number(item.expenses || 0);
      }
    });
    filtered = Object.entries(monthMap).map(([ym, expenses]) => ({ ym, expenses }));
  } else {
    filtered = (Array.isArray(data) ? data : []).filter(
      item => item && typeof item.ym === "string" && item.category === category
    );
  }
  // Sort descending by ym
  const sorted = [...filtered].sort((a, b) => b.ym.localeCompare(a.ym));
  // Take last 6
  const last6 = sorted.slice(0, 6);
  // Sort ascending for chart display
  return last6.sort((a, b) => a.ym.localeCompare(b.ym));
}

async function fetchMonthlyData(category = "total") {
  console.debug("[monthly] fetchMonthlyData", { category });
  try {
    const res = await fetch(`/statistics/monthly?category=${encodeURIComponent(category)}`, { credentials: "same-origin" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    console.debug("[monthly] fetched", { len: Array.isArray(json) ? json.length : 0 });
    return json;
  } catch (err) {
    console.warn("[monthly] fetch failed, falling back to inline monthly-data", err);
    return readJSONScript("monthly-data");
  }
}

async function renderChart(category = "total") {
  console.debug("[monthly] renderChart start", { category });
  const last6Data = await fetchMonthlyData(category);
  console.debug("[monthly] renderChart data sample", last6Data?.slice?.(0, 3));
  const el = by("monthly-chart");
  if (!el || !window.Chart) {
    console.warn("[monthly] canvas or Chart.js missing");
    return;
  }
  const ctx = el.getContext("2d");
  if (el._chartInstance) {
    el._chartInstance.destroy();
  }
  el._chartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels(last6Data, "ym"),
      datasets: [{
        label: category === "total" ? "הוצאות חודשיות (₪)" : `הוצאות (${category}) (₪)`,
        data: values(last6Data, "expenses"),
        borderWidth: 0,
        borderRadius: 10,
      }]
    },
    options: {
      ...baseOptions,
      scales: {
        ...baseOptions.scales,
        x: { ...baseOptions.scales.x, ticks: { ...baseOptions.scales.x.ticks, font: { size: 12 } } },
        y: { ...baseOptions.scales.y, ticks: { ...baseOptions.scales.y.ticks, font: { size: 12 } } }
      }
    }
  });
  console.debug("[monthly] chart rendered");
}

// Initial render
renderChart();

// Listen for category change
const categorySelect = by("monthly-category");
if (categorySelect) {
  categorySelect.addEventListener("change", (e) => {
    renderChart(e.target.value);
  });
}
