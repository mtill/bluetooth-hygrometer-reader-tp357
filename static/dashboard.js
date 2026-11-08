const metricSelect = document.querySelector("#metric");
const dateSelect = document.querySelector("#date");
const canvas = document.querySelector("#chart");
const legend = document.querySelector("#legend");
const status = document.querySelector("#status");
const context = canvas.getContext("2d");
let latestData = null;
const colors = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#be123c", "#4d7c0f"];
let sensorColors = new Map();

async function requestJson(url) {
  const response = await fetch(url, {cache: "no-store"});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

function setOptions(select, values, selected) {
  select.replaceChildren(...values.map(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = value === selected;
    return option;
  }));
}

async function refreshDates() {
  const query = new URLSearchParams({metric: metricSelect.value});
  const options = await requestJson(`/api/options?${query}`);
  sensorColors = new Map(options.locations.map((location, index) => [
    location,
    options.sensorColors[location] || colors[index % colors.length]
  ]));
  const oldDate = dateSelect.value;
  setOptions(dateSelect, options.dates, options.dates.includes(oldDate) ? oldDate : options.dates.at(-1));
  await refreshChart();
}

async function refreshChart() {
  if (!dateSelect.value) {
    latestData = null;
    legend.replaceChildren();
    drawChart();
    status.textContent = "No readings found.";
    return;
  }
  const query = new URLSearchParams({
    metric: metricSelect.value,
    date: dateSelect.value
  });
  latestData = await requestJson(`/api/data?${query}`);
  drawChart();
  status.textContent = `${latestData.sensorCount} sensors · ${latestData.readingCount} readings · refreshed ${new Date().toLocaleTimeString()}`;
}

function drawChart() {
  const ratio = window.devicePixelRatio || 1;
  const bounds = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.round(bounds.width * ratio));
  canvas.height = Math.max(1, Math.round(bounds.height * ratio));
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, bounds.width, bounds.height);
  const series = latestData?.series || [];
  legend.replaceChildren(...series.map(item => {
    const entry = document.createElement("span");
    entry.className = "legend-item";
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.backgroundColor = sensorColors.get(item.location) || colors[0];
    const label = document.createElement("span");
    label.textContent = item.location;
    entry.append(swatch, label);
    return entry;
  }));
  const points = series.flatMap(item => item.points);
  if (!points.length) {
    context.fillStyle = "#64748b";
    context.font = "14px system-ui, sans-serif";
    context.textAlign = "center";
    context.fillText("No readings for this date", bounds.width / 2, bounds.height / 2);
    return;
  }

  const left = 54, right = 18, top = 18, bottom = 36;
  const width = Math.max(1, bounds.width - left - right);
  const height = Math.max(1, bounds.height - top - bottom);
  const values = points.map(point => point.value);
  let min = Math.min(...values), max = Math.max(...values);
  if (min === max) { min -= 1; max += 1; }
  const pad = (max - min) * .12;
  min -= pad; max += pad;
  const lastSecondOfDay = 24 * 60 * 60 - 1;
  const x = time => left + time * width / lastSecondOfDay;
  const y = value => top + (max - value) * height / (max - min);

  context.font = "12px system-ui, sans-serif";
  context.textAlign = "right";
  context.textBaseline = "middle";
  context.strokeStyle = "#e8edf4";
  context.fillStyle = "#64748b";
  for (let tick = 0; tick <= 4; tick++) {
    const value = min + (max - min) * tick / 4;
    const yPos = top + height * (1 - tick / 4);
    context.beginPath();
    context.moveTo(left, yPos);
    context.lineTo(left + width, yPos);
    context.stroke();
    context.fillText(`${value.toFixed(1)}${latestData.unit}`, left - 9, yPos);
  }

  series.forEach((item, seriesIndex) => {
    const color = sensorColors.get(item.location) || colors[seriesIndex % colors.length];
    context.strokeStyle = color;
    context.lineWidth = 2;
    context.lineJoin = "round";
    context.beginPath();
    item.points.forEach((point, index) => {
      if (index === 0) context.moveTo(x(point.timeSeconds), y(point.value));
      else context.lineTo(x(point.timeSeconds), y(point.value));
    });
    context.stroke();
    context.fillStyle = color;
    item.points.forEach(point => {
      context.beginPath();
      context.arc(x(point.timeSeconds), y(point.value), item.points.length < 80 ? 2.5 : 1.5, 0, Math.PI * 2);
      context.fill();
    });
  });

  context.fillStyle = "#64748b";
  context.textAlign = "left";
  context.textBaseline = "top";
  context.fillText("00:00:00", left, top + height + 12);
  context.textAlign = "right";
  context.fillText("23:59:59", left + width, top + height + 12);
  document.title = `${latestData.label} · Hygrometer`;
}

async function initialize() {
  try {
    const options = await requestJson("/api/options");
    if (!options.dates.length) {
      status.textContent = "No sensor data found. Start the reader to create readings.";
      drawChart();
      return;
    }
    await refreshDates();
  } catch (error) {
    status.textContent = error.message;
  }
}

metricSelect.addEventListener("change", () => refreshDates().catch(showError));
dateSelect.addEventListener("change", () => refreshChart().catch(showError));
window.addEventListener("resize", drawChart);
window.setInterval(() => {
  if (dateSelect.value) refreshChart().catch(showError);
}, 60000);
function showError(error) { status.textContent = error.message; }
initialize();
