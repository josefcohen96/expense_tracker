import { Chart } from '../vendor/chart.umd.min.js';

export function initUserBar(ctx, labels, values) {
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'הוצאות קבועות לפי חודש',
        data: values,
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
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              return context.parsed.y.toLocaleString('he-IL') + ' ₪';
            }
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback: function(value) {
              return value.toLocaleString('he-IL') + ' ₪';
            }
          }
        }
      }
    }
  });
}
