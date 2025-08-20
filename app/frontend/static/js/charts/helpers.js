export const by = (id) => document.getElementById(id);

export const readJSONScript = (id) => {
  const el = by(id);
  if (!el) return [];
  try { return JSON.parse(el.textContent || "[]"); } catch { return []; }
};

export const labels = (arr, key) => arr.map((o) => o?.[key]);
export const values = (arr, key) => arr.map((o) => Number(o?.[key] || 0));

export const fmtCurrency = (n) =>
  new Intl.NumberFormat("he-IL", { style: "currency", currency: "ILS", maximumFractionDigits: 0 }).format(n);

// סט אופציות בסיס לכל הגרפים (RTL, מרווחים, פונט)
export const baseOptions = {
  responsive: true,
  maintainAspectRatio: false, // חשוב כדי שהגרף ימלא את הקונטיינר
  locale: "he-IL",
  layout: { padding: { top: 8, right: 8, bottom: 8, left: 8 } },
  plugins: {
    legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
    tooltip: {
      rtl: true,
      callbacks: {
        label: (ctx) => fmtCurrency(ctx.parsed.y ?? ctx.parsed)
      }
    }
  },
  scales: {
    x: {
      ticks: { maxRotation: 0, autoSkip: true },
      grid: { display: false }
    },
    y: {
      beginAtZero: true,
      grid: { color: "rgba(0,0,0,0.06)" },
      ticks: {
        callback: (v) => new Intl.NumberFormat("he-IL", { notation: "compact" }).format(v)
      }
    }
  }
};
