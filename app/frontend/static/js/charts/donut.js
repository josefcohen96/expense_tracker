import { by, readJSONScript, labels, values, baseOptions } from "./helpers.js";

const data = readJSONScript("category-data");
const el = by("donut-chart");
if (el && window.Chart) {
  const ctx = el.getContext("2d");
  new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: labels(data, "category"),
      datasets: [{
        label: "₪",
        data: values(data, "total")
      }]
    },
    options: {
      ...baseOptions,
      plugins: {
        ...baseOptions.plugins,
        legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 10 } }
      },
      cutout: "62%" // דונאט אלגנטי יותר
    }
  });
}
