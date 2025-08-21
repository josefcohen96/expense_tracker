export function by(id) {
	return document.getElementById(id);
}

export function readJSONScript(scriptId) {
	const node = document.getElementById(scriptId);
	if (!node) {
		return [];
	}
	try {
		const result = JSON.parse(node.textContent || "[]");
		return result;
	} catch (error) {
		console.error(`Error parsing JSON for ${scriptId}:`, error);
		return [];
	}
}

export function labels(arr, key) {
	return (Array.isArray(arr) ? arr : []).map(it => it?.[key] ?? "");
}

export function values(arr, key) {
	return (Array.isArray(arr) ? arr : []).map(it => Number(it?.[key] ?? 0));
}

export const baseOptions = {
	responsive: true,
	maintainAspectRatio: false,
	plugins: {
		legend: { position: "right" },
		tooltip: {
			callbacks: {
				label: (ctx) => {
					const v = ctx.parsed?.y ?? ctx.parsed ?? ctx.raw;
					return `${ctx.label || ""}: ${Number(v).toLocaleString()}`;
				}
			}
		}
	},
	scales: {
		x: { grid: { display: false }, ticks: { color: "#334155" } },
		y: {
			beginAtZero: true,
			grid: { color: "rgba(148,163,184,0.2)" },
			ticks: { color: "#334155", callback: (v) => Number(v).toLocaleString() }
		}
	}
};

