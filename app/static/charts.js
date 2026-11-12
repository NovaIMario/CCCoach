// Charts for the profile and compare pages (Chart.js).

const css = getComputedStyle(document.documentElement);
const ink = css.getPropertyValue("--muted").trim();
const grid = css.getPropertyValue("--line").trim();
const SERIES = [css.getPropertyValue("--accent").trim(), css.getPropertyValue("--accent2").trim()];

Chart.defaults.color = ink;
Chart.defaults.borderColor = grid;
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;

function historyChart(series) {
  new Chart(document.getElementById("history"), {
    type: "line",
    data: {
      datasets: series.map((s, i) => ({
        label: s.label,
        data: s.data.map(c => ({ x: c.t * 1000, y: c.r, contest: c.contest })),
        borderColor: SERIES[i], backgroundColor: SERIES[i], pointRadius: 2, borderWidth: 2, tension: 0.15,
      })),
    },
    options: {
      parsing: false,
      scales: {
        x: { type: "linear", ticks: { callback: v => new Date(v).getFullYear() } },
        y: { title: { display: true, text: "Rating" } },
      },
      plugins: {
        legend: { display: series.length > 1 },
        tooltip: { callbacks: {
          title: items => items[0].raw.contest,
          label: item => `${item.dataset.label}: ${item.raw.y}`,
        } },
      },
    },
  });
}

if (typeof HISTORY !== "undefined") {
  historyChart([{ label: "Rating", data: HISTORY }]);
  const keys = Object.keys(SOLVED);
  new Chart(document.getElementById("solvedHist"), {
    type: "bar",
    data: { labels: keys, datasets: [{ label: "Solved", data: keys.map(k => SOLVED[k]), backgroundColor: SERIES[0], borderRadius: 3 }] },
    options: { plugins: { legend: { display: false } }, scales: { x: { title: { display: true, text: "Problem rating" } } } },
  });
}

if (typeof COMPARE !== "undefined") historyChart(COMPARE);
