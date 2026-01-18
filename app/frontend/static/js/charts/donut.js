import { readJSONScript } from "./helpers.js";

// Read category data from the page JSON script
const rawCategoryData = readJSONScript("category-data");

// Normalize to { month: 'YYYY-MM', category: string, amount: number }
const categoryItems = (rawCategoryData || [])
	.map((it) => {
		const amount = it.amount ?? it.total ?? it.sum ?? 0;
		return {
			month: (it.month ?? it.ym ?? it.period ?? "").toString(),
			category: it.category ?? it.name ?? it.title ?? "אחר",
			amount: Number(amount) || 0,
		};
	})
	.filter((x) => x.amount !== 0 && x.month);

// Available months (sorted lexicographically: YYYY-MM)
const availableMonths = Array.from(new Set(categoryItems.map((m) => m.month)))
	.filter(Boolean)
	.sort();

// UI elements
const inputMonth = document.getElementById("donut-month-single");
const ctx = document.getElementById("donut-chart");

// Helpers
function getCurrentMonth() {
	const d = new Date();
	const y = d.getFullYear();
	const m = String(d.getMonth() + 1).padStart(2, "0");
	return `${y}-${m}`;
}

function setDefaultMonth() {
	const current = getCurrentMonth();
	// Respect a server-provided value (statistics page global month)
	if (inputMonth && inputMonth.value) {
		return;
	}
	if (!availableMonths.length) {
		if (inputMonth && !inputMonth.value) inputMonth.value = current;
		return;
	}
	const last = availableMonths[availableMonths.length - 1];
	if (inputMonth) inputMonth.value = availableMonths.includes(current) ? current : last;
}

// Aggregate a single month to category totals
function aggregateForMonth(month) {
	const acc = new Map();
	for (const item of categoryItems) {
		if (item.month !== month) continue;
		acc.set(item.category, (acc.get(item.category) || 0) + item.amount);
	}
	const labels = Array.from(acc.keys());
	const data = labels.map((l) => acc.get(l) || 0);
	return { labels, data };
}

// Generate colors for categories
function generateColors(count) {
	const colors = [];
	for (let i = 0; i < count; i++) {
		const hue = Math.floor((360 / Math.max(1, count)) * i);
		colors.push(`hsl(${hue}, 70%, 55%)`);
	}
	return colors;
}

// Chart instance
let chart;

function renderChart() {
	const selectedMonth = inputMonth.value || getCurrentMonth();
	let { labels, data } = aggregateForMonth(selectedMonth);

	// If no data, show placeholder
	if (!labels.length || !data.length || data.every((v) => v === 0)) {
		labels = ["אין נתונים"];
		data = [1];
	}

	const backgroundColor = generateColors(labels.length);
	const dataset = {
		label: "סכום",
		data,
		backgroundColor,
		borderWidth: 0
	};

	if (!chart) {
		chart = new Chart(ctx, {
			type: "doughnut",
			data: { labels, datasets: [dataset] },
			options: {
				responsive: true,
				maintainAspectRatio: false,
				onClick: (evt, elements, chart) => {
					if (elements && elements.length > 0) {
						const index = elements[0].index;
						const label = chart.data.labels[index];
						const selectedMonth = document.getElementById("donut-month-single").value;
						if (window.openDrilldownModal) {
							window.openDrilldownModal({ category: label, month: selectedMonth });
						}
					}
				},
				plugins: {
					legend: {
						position: "right",
						labels: {
							font: {
								size: 12
							}
						}
					},
					tooltip: {
						callbacks: {
							label: (item) => {
								const value = item.parsed;
								const label = item.label || "";
								return `${label}: ${Number(value).toLocaleString()} ₪`;
							},
						},
					},
				},
			},
		});
	} else {
		chart.data.labels = labels;
		chart.data.datasets[0].data = data;
		chart.data.datasets[0].backgroundColor = backgroundColor;
		chart.update();
	}
}

// Initialize
setDefaultMonth();
renderChart();

// Event listeners
if (inputMonth) inputMonth.addEventListener("change", renderChart);
