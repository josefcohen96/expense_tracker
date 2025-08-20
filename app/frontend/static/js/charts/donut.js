import { by, readJSONScript, labels, values } from "./helpers.js";

const data = readJSONScript("category-data");
const ctx = by("donut-chart").getContext("2d");

new Chart(ctx, {
  type: "doughnut",
  data: {
    labels: labels(data, "category"),
    datasets: [{
      label: "הוצאות לפי קטגוריה",
      data: values(data, "total"),
      backgroundColor: [
        "#6366F1", "#EC4899", "#10B981", "#F59E0B",
        "#3B82F6", "#EF4444", "#8B5CF6", "#14B8A6"
      ]
    }]
  },
  options: {
    responsive: true,
    plugins: { legend: { position: "bottom" } }
  }
});
