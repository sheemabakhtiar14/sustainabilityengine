const form = document.querySelector("#comparison-form");
const recycledValue = document.querySelector("#recycled-value");
const selectionNote = document.querySelector("#selection-note");
const cardsTarget = document.querySelector("#comparison-cards");
const tableTarget = document.querySelector("#comparison-table");

let updateTimer;

function checkedMetals() {
  return [...form.querySelectorAll('input[name="metals"]:checked')].map((input) => input.value);
}

function collectInputs() {
  const values = {};
  const formData = new FormData(form);

  formData.forEach((value, key) => {
    if (key !== "metals") {
      values[key] = Number(value);
    }
  });

  values.metals = checkedMetals();
  return values;
}

function formatNumber(value, digits = 0) {
  return Number(value).toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function enforceSelectionLimit(changedInput) {
  const selected = checkedMetals();

  if (selected.length > 3) {
    changedInput.checked = false;
  }

  const count = checkedMetals().length;
  selectionNote.textContent =
    count < 2 ? "Pick at least 2 metals." : `${count} metal${count === 1 ? "" : "s"} selected.`;
  selectionNote.classList.toggle("warn-text", count < 2);
}

function renderCards(rows) {
  cardsTarget.innerHTML = rows
    .map(
      (row) => `
        <article class="comparison-card">
          <h3>${row.metal}</h3>
          <p>${row.source}</p>
          <div class="comparison-stats">
            <div class="comparison-stat"><span>Red Mud Feed</span><strong>${formatNumber(row.red_mud_feed_required)} kg</strong></div>
            <div class="comparison-stat"><span>Operational CO2</span><strong>${formatNumber(row.total_co2)} kg</strong></div>
            <div class="comparison-stat"><span>Total Energy</span><strong>${formatNumber(row.total_energy)} kWh</strong></div>
            <div class="comparison-stat"><span>Recovery</span><strong>${formatNumber(row.recovery_percent, 1)}%</strong></div>
            <div class="comparison-stat"><span>Energy</span><strong>${formatNumber(row.metal_energy)} kWh</strong></div>
            <div class="comparison-stat"><span>Input Water</span><strong>${formatNumber(row.input_water)} L</strong></div>
            <div class="comparison-stat"><span>Water</span><strong>${formatNumber(row.metal_water)} L</strong></div>
            <div class="comparison-stat"><span>Process CO2</span><strong>${formatNumber(row.metal_process_co2)} kg</strong></div>
            <div class="comparison-stat"><span>Circularity</span><strong>${formatNumber(row.circularity_score, 1)}</strong></div>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderTable(rows) {
  tableTarget.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${row.metal}</td>
          <td>${formatNumber(row.grade_percent, 4)}</td>
          <td>${formatNumber(row.recovery_percent, 1)}</td>
          <td>${formatNumber(row.red_mud_feed_required)}</td>
          <td>${formatNumber(row.total_co2)}</td>
          <td>${formatNumber(row.total_energy)}</td>
          <td>${formatNumber(row.input_water)}</td>
          <td>${formatNumber(row.metal_energy)}</td>
          <td>${formatNumber(row.metal_water)}</td>
          <td>${formatNumber(row.metal_process_co2)}</td>
          <td>${formatNumber(row.circularity_score, 1)}</td>
        </tr>
      `,
    )
    .join("");
}

function renderChart(chart) {
  Plotly.react("comparison-chart", chart.data, chart.layout, {
    responsive: true,
    displayModeBar: false,
  });
}

async function refreshComparison() {
  const inputs = collectInputs();
  recycledValue.textContent = inputs.recycled_content;

  if (inputs.metals.length < 2) {
    return;
  }

  const response = await fetch("/api/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(inputs),
  });

  if (!response.ok) {
    throw new Error("Could not compare metals");
  }

  const payload = await response.json();
  renderCards(payload.rows);
  renderTable(payload.rows);
  renderChart(payload.chart);
}

function scheduleRefresh(event) {
  if (event?.target?.name === "metals") {
    enforceSelectionLimit(event.target);
  }

  window.clearTimeout(updateTimer);
  updateTimer = window.setTimeout(() => {
    refreshComparison().catch((error) => {
      cardsTarget.innerHTML = `<div class="insight-card warn">${error.message}</div>`;
    });
  }, 150);
}

form.addEventListener("input", scheduleRefresh);
form.addEventListener("change", scheduleRefresh);

window.addEventListener("resize", () => Plotly.Plots.resize("comparison-chart"));

selectionNote.textContent = `${checkedMetals().length} metals selected.`;
refreshComparison();
