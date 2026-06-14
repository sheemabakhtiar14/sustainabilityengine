const form = document.querySelector("#metrics-form");
const tableBody = document.querySelector("#metrics-table");
const recycledValue = document.querySelector("#recycled-value");
const downloadLink = document.querySelector("#download-link");
const insightsButton = document.querySelector("#insights-button");
const insightsContainer = document.querySelector("#insights");
const INSIGHTS_TIMEOUT_MS = 30000;

const chartTargets = {
  emissions: "emissions-chart",
  performance: "performance-chart",
  material: "material-chart",
  circularity: "circularity-chart",
};

let latestInputs = {};
let updateTimer;
let sharedSnapshot = "";
let applyingSharedInputs = false;

function collectInputs() {
  const data = {};
  const formData = new FormData(form);

  formData.forEach((value, key) => {
    data[key] = key === "metal_type" ? value : Number(value);
  });

  return data;
}

function queryStringFromInputs(inputs) {
  return new URLSearchParams(inputs).toString();
}

function sharedOnly(inputs) {
  return {
    production_amount: inputs.production_amount,
    useful_output: inputs.useful_output,
    waste_generated: inputs.waste_generated,
    recovered_material: inputs.recovered_material,
    recycled_content: inputs.recycled_content,
  };
}

function sharedSignature(inputs) {
  return JSON.stringify(sharedOnly(inputs));
}

function applySharedInputs(shared) {
  let changed = false;

  Object.entries(shared).forEach(([key, value]) => {
    const input = form.elements[key];
    if (!input || Number(input.value) === Number(value)) {
      return;
    }

    input.value = value;
    changed = true;
  });

  if (changed) {
    applyingSharedInputs = true;
    refreshDashboard()
      .catch((error) => {
        insightsContainer.innerHTML = `<div class="insight-card warn">${error.message}</div>`;
      })
      .finally(() => {
        applyingSharedInputs = false;
      });
  }
}

function updateCards(cards) {
  Object.entries(cards).forEach(([key, card]) => {
    const valueTarget = document.querySelector(`[data-card="${key}"]`);
    const unitTarget = document.querySelector(`[data-card-unit="${key}"]`);

    if (valueTarget) {
      valueTarget.textContent = card.value;
    }

    if (unitTarget) {
      unitTarget.textContent = card.unit;
    }
  });
}

function updateTable(rows) {
  tableBody.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${row.Metric}</td>
          <td>${row.Value}</td>
        </tr>
      `,
    )
    .join("");
}

function renderChart(name, chart) {
  const target = chartTargets[name];
  const config = { responsive: true, displayModeBar: false };
  Plotly.react(target, chart.data, chart.layout, config);
}

function updateCharts(charts) {
  Object.entries(charts).forEach(([name, chart]) => renderChart(name, chart));
}

function classifyInsight(line) {
  const normalized = line.toLowerCase();
  if (normalized.startsWith("warning") || normalized.includes("warning")) {
    return "insight-card warn";
  }
  if (normalized.startsWith("tip") || normalized.includes("improve")) {
    return "insight-card info";
  }
  return "insight-card";
}

function renderInsights(text) {
  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  insightsContainer.innerHTML = lines
    .map((line) => `<div class="${classifyInsight(line)}">${line}</div>`)
    .join("");
}

async function refreshDashboard() {
  latestInputs = collectInputs();
  recycledValue.textContent = latestInputs.recycled_content;
  downloadLink.href = `/download?${queryStringFromInputs(latestInputs)}`;

  const response = await fetch("/api/calculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(latestInputs),
  });

  if (!response.ok) {
    throw new Error("Could not update metrics");
  }

  const payload = await response.json();
  sharedSnapshot = sharedSignature(payload.inputs);
  updateCards(payload.cards);
  updateTable(payload.table);
  updateCharts(payload.charts);
}

function scheduleRefresh() {
  window.clearTimeout(updateTimer);
  updateTimer = window.setTimeout(() => {
    refreshDashboard().catch((error) => {
      insightsContainer.innerHTML = `<div class="insight-card warn">${error.message}</div>`;
    });
  }, 150);
}

form.addEventListener("input", scheduleRefresh);
form.addEventListener("change", scheduleRefresh);

async function syncSharedInputs() {
  if (applyingSharedInputs) {
    return;
  }

  try {
    const response = await fetch("/api/shared");
    if (!response.ok) {
      return;
    }

    const shared = await response.json();
    const signature = sharedSignature({ ...collectInputs(), ...shared });
    if (signature !== sharedSnapshot) {
      sharedSnapshot = signature;
      applySharedInputs(shared);
    }
  } catch (error) {
    // Keep the dashboard usable if the peer app is not running yet.
  }
}

insightsButton.addEventListener("click", async () => {
  insightsButton.disabled = true;
  insightsButton.textContent = "Analysing sustainability data...";
  insightsContainer.innerHTML = "";
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), INSIGHTS_TIMEOUT_MS);

  try {
    const response = await fetch("/api/insights", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectInputs()),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error("Could not fetch Gemini insights");
    }

    const payload = await response.json();
    renderInsights(payload.insights);
  } catch (error) {
    const message =
      error.name === "AbortError"
        ? "Gemini took too long to respond. Please try again."
        : error.message;
    insightsContainer.innerHTML = `<div class="insight-card warn">${message}</div>`;
  } finally {
    window.clearTimeout(timeout);
    insightsButton.disabled = false;
    insightsButton.textContent = "Generate AI Insights with Gemini";
  }
});

window.addEventListener("resize", () => {
  Object.values(chartTargets).forEach((target) => Plotly.Plots.resize(target));
});

refreshDashboard();
window.setInterval(syncSharedInputs, 1000);
