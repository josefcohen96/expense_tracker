import { by, baseOptions } from "./helpers.js";

// Year-over-year comparison: monthly expenses for the current year vs the
// previous year, fetched from /api/statistics/yearly-comparison.

const HEB_MONTHS = ["ינו", "פבר", "מרץ", "אפר", "מאי", "יונ", "יול", "אוג", "ספט", "אוק", "נוב", "דצמ"];

async function fetchYearlyData() {
  const res = await fetch("/api/statistics/yearly-comparison", { credentials: "same-origin" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function formatShekels(value) {
  return `₪${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function renderSummary(data) {
  const summary = by("yearly-summary");
  if (!summary) return;

  const currentLabel = by("yearly-current-label");
  const previousLabel = by("yearly-previous-label");
  const currentValue = by("yearly-current-value");
  const previousValue = by("yearly-previous-value");
  const changeEl = by("yearly-change");

  if (currentLabel) currentLabel.textContent = `הוצאות ${data.current_year} (עד כה)`;
  if (previousLabel) previousLabel.textContent = `אותה תקופה ב-${data.previous_year}`;
  if (currentValue) currentValue.textContent = formatShekels(data.current_ytd);
  if (previousValue) previousValue.textContent = formatShekels(data.previous_ytd);

  if (changeEl) {
    if (data.previous_ytd > 0) {
      const pct = Number(data.ytd_change_pct || 0);
      const up = pct > 0;
      // More spending than last year is bad (red), less is good (green)
      changeEl.textContent = `${up ? "▲" : "▼"} ${Math.abs(pct).toFixed(1)}%`;
      changeEl.classList.add(up ? "text-red-600" : "text-green-600");
    } else {
      changeEl.textContent = "—";
      changeEl.classList.add("text-gray-400");
    }
  }

  summary.style.display = "grid";
}

function renderChart(data) {
  const el = by("yearly-chart");
  if (!el || !window.Chart) {
    console.warn("[yearly] canvas or Chart.js missing");
    return;
  }
  const ctx = el.getContext("2d");
  if (el._chartInstance) {
    el._chartInstance.destroy();
  }
  el._chartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: HEB_MONTHS,
      datasets: [
        {
          label: `${data.previous_year} (₪)`,
          data: data.previous,
          backgroundColor: "rgba(148, 163, 184, 0.55)",
          borderWidth: 0,
          borderRadius: 6,
        },
        {
          label: `${data.current_year} (₪)`,
          data: data.current,
          backgroundColor: "rgba(99, 102, 241, 0.85)",
          borderWidth: 0,
          borderRadius: 6,
        },
      ],
    },
    options: {
      ...baseOptions,
      plugins: {
        ...baseOptions.plugins,
        legend: { position: "top" },
      },
      scales: {
        ...baseOptions.scales,
        x: { ...baseOptions.scales.x, ticks: { ...baseOptions.scales.x.ticks, font: { size: 12 } } },
        y: { ...baseOptions.scales.y, ticks: { ...baseOptions.scales.y.ticks, font: { size: 12 } } },
      },
    },
  });
}

async function init() {
  try {
    const data = await fetchYearlyData();
    renderSummary(data);
    renderChart(data);
  } catch (err) {
    console.warn("[yearly] failed to load year-over-year data", err);
  }
}

init();
