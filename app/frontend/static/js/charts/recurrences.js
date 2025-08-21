import { by, readJSONScript, labels, values, baseOptions } from "./helpers.js";

// recurrences-data should be an array of objects like:
// { month: '2025-03', total: 1250.50 }

function getLast6Months(data) {
  // Filter and sort the data to get last 6 months
  const filtered = (Array.isArray(data) ? data : []).filter(
    item => item && typeof item.month === "string"
  );
  
  // Sort descending by month
  const sorted = [...filtered].sort((a, b) => b.month.localeCompare(a.month));
  // Take last 6
  const last6 = sorted.slice(0, 6);
  // Sort ascending for chart display
  return last6.sort((a, b) => a.month.localeCompare(b.month));
}

async function fetchRecurrencesData() {
  console.debug("[recurrences] fetchRecurrencesData");
  try {
    const res = await fetch(`/api/statistics/recurrences`, { credentials: "same-origin" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    console.debug("[recurrences] fetched", { len: Array.isArray(json) ? json.length : 0 });
    return json;
  } catch (err) {
    console.warn("[recurrences] fetch failed, falling back to inline recurrences-data", err);
    return readJSONScript("recurrences-data");
  }
}

async function renderChart() {
  console.debug("[recurrences] renderChart start");
  const last6Data = await fetchRecurrencesData();
  console.debug("[recurrences] renderChart data sample", last6Data?.slice?.(0, 3));
  const el = by("recurrences-chart");
  if (!el || !window.Chart) {
    console.warn("[recurrences] canvas or Chart.js missing");
    return;
  }
  const ctx = el.getContext("2d");
  if (el._chartInstance) {
    el._chartInstance.destroy();
  }
  el._chartInstance = new window.Chart(ctx, {
    type: "bar",
    data: {
      labels: labels(last6Data, "month"),
      datasets: [{
        label: "הוצאות קבועות חודשיות (₪)",
        data: values(last6Data, "total"),
        backgroundColor: [
          'rgba(139, 69, 19, 0.8)',   // חום
          'rgba(85, 107, 47, 0.8)',   // ירוק זית
          'rgba(112, 128, 144, 0.8)', // אפור כחול
          'rgba(205, 133, 63, 0.8)',  // חום בהיר
          'rgba(128, 128, 0, 0.8)',   // זית
          'rgba(95, 158, 160, 0.8)'   // ירוק ים כהה
        ],
        borderColor: [
          'rgba(139, 69, 19, 1)',     // חום
          'rgba(85, 107, 47, 1)',     // ירוק זית
          'rgba(112, 128, 144, 1)',   // אפור כחול
          'rgba(205, 133, 63, 1)',    // חום בהיר
          'rgba(128, 128, 0, 1)',     // זית
          'rgba(95, 158, 160, 1)'     // ירוק ים כהה
        ],
        borderWidth: 1,
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
  console.debug("[recurrences] chart rendered");
}

// Initial render
renderChart();
