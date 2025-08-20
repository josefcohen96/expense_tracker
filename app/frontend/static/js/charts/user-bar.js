import { by, readJSONScript, labels, values } from "./helpers.js";

const data = readJSONScript("user-data");
const ctx = by("user-chart").getContext("2d");

new Chart(ctx, {
  type: "bar",
  data: {
    labels: labels(data, "user"),
    datasets: [{
      label: "הוצאות לפי משתמש",
      data: values(data, "total"),
      backgroundColor: ["rgba(16, 185, 129, 0.7)", "rgba(239, 68, 68, 0.7)"]
    }]
  },
  options: { responsive: true }
});
