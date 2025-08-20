import { by, readJSONScript, labels, values } from "./helpers.js";

const data = readJSONScript("monthly-data");
const ctx = by("monthly-chart").getContext("2d");

new Chart(ctx, {
  type: "bar",
  data: {
    labels: labels(data, "month"),
    datasets: [{
      label: "הוצאות חודשיות",
      data: values(data, "total"),
      backgroundColor: "rgba(99, 102, 241, 0.7)"
    }]
  },
  options: { responsive: true }
});
