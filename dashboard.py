#!/usr/bin/env python3
# coding=utf-8

import argparse
from datetime import date
import json
import logging
from pathlib import Path
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
METRICS = {
    "temperature": ("_temperature", "Temperature", "°C"),
    "humidity": ("_humidity", "Humidity", "%"),
}

PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hygrometer readings</title>
  <style>
    :root { color-scheme: light; font-family: system-ui, sans-serif; color: #172033; background: #f3f6fb; }
    * { box-sizing: border-box; }
    body { margin: 0; padding: 32px 18px; }
    main { max-width: 1000px; margin: auto; }
    h1 { margin: 0 0 6px; font-size: clamp(1.5rem, 4vw, 2rem); }
    .subtitle { margin: 0 0 24px; color: #64748b; }
    .panel { padding: 22px; background: white; border: 1px solid #e2e8f0; border-radius: 14px; box-shadow: 0 8px 26px #0f172a0b; }
    .controls { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 20px; }
    label { display: grid; gap: 6px; color: #475569; font-size: .88rem; font-weight: 600; }
    select { min-width: 150px; padding: 9px 32px 9px 10px; border: 1px solid #cbd5e1; border-radius: 8px; background: white; color: #172033; font: inherit; }
    .chart-wrap { position: relative; height: min(58vh, 430px); min-height: 260px; }
    canvas { width: 100%; height: 100%; display: block; }
    #status { min-height: 1.5em; margin: 12px 0 0; color: #64748b; font-size: .9rem; }
    @media (max-width: 520px) { body { padding: 22px 12px; } .panel { padding: 15px; } .controls { gap: 10px; } label, select { width: 100%; } }
  </style>
</head>
<body>
  <main>
    <h1>Hygrometer readings</h1>
    <p class="subtitle">Temperature and humidity history from your sensors</p>
    <section class="panel">
      <div class="controls">
        <label>Location<select id="location"></select></label>
        <label>Reading<select id="metric">
          <option value="temperature">Temperature</option>
          <option value="humidity">Humidity</option>
        </select></label>
        <label>Date<select id="date"></select></label>
      </div>
      <div class="chart-wrap"><canvas id="chart" aria-label="Sensor readings chart"></canvas></div>
      <p id="status" role="status"></p>
    </section>
  </main>
<script>
const locationSelect = document.querySelector("#location");
const metricSelect = document.querySelector("#metric");
const dateSelect = document.querySelector("#date");
const canvas = document.querySelector("#chart");
const status = document.querySelector("#status");
const context = canvas.getContext("2d");
let latestData = null;

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
  const query = new URLSearchParams({
    location: locationSelect.value,
    metric: metricSelect.value
  });
  const options = await requestJson(`/api/options?${query}`);
  const oldDate = dateSelect.value;
  setOptions(dateSelect, options.dates, options.dates.includes(oldDate) ? oldDate : options.dates.at(-1));
  await refreshChart();
}

async function refreshChart() {
  if (!locationSelect.value || !dateSelect.value) {
    latestData = null;
    drawChart();
    status.textContent = "No readings found.";
    return;
  }
  const query = new URLSearchParams({
    location: locationSelect.value,
    metric: metricSelect.value,
    date: dateSelect.value
  });
  latestData = await requestJson(`/api/data?${query}`);
  drawChart();
  status.textContent = `${latestData.points.length} readings · refreshed ${new Date().toLocaleTimeString()}`;
}

function drawChart() {
  const ratio = window.devicePixelRatio || 1;
  const bounds = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.round(bounds.width * ratio));
  canvas.height = Math.max(1, Math.round(bounds.height * ratio));
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, bounds.width, bounds.height);
  const points = latestData?.points || [];
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
  const x = index => left + (points.length === 1 ? width / 2 : index * width / (points.length - 1));
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

  context.strokeStyle = "#2563eb";
  context.lineWidth = 2.5;
  context.lineJoin = "round";
  context.beginPath();
  points.forEach((point, index) => {
    if (index === 0) context.moveTo(x(index), y(point.value));
    else context.lineTo(x(index), y(point.value));
  });
  context.stroke();
  context.fillStyle = "#2563eb";
  points.forEach((point, index) => {
    context.beginPath();
    context.arc(x(index), y(point.value), points.length < 80 ? 2.5 : 1.5, 0, Math.PI * 2);
    context.fill();
  });

  context.fillStyle = "#64748b";
  context.textAlign = "left";
  context.textBaseline = "top";
  context.fillText(points[0].time, left, top + height + 12);
  context.textAlign = "right";
  context.fillText(points.at(-1).time, left + width, top + height + 12);
  document.title = `${latestData.location} ${latestData.label} · Hygrometer`;
}

async function initialize() {
  try {
    const options = await requestJson("/api/options");
    setOptions(locationSelect, options.locations, options.locations[0]);
    if (!options.locations.length) {
      status.textContent = "No sensor data found. Start the reader to create readings.";
      drawChart();
      return;
    }
    await refreshDates();
  } catch (error) {
    status.textContent = error.message;
  }
}

locationSelect.addEventListener("change", () => refreshDates().catch(showError));
metricSelect.addEventListener("change", () => refreshDates().catch(showError));
dateSelect.addEventListener("change", () => refreshChart().catch(showError));
window.addEventListener("resize", drawChart);
window.setInterval(() => {
  if (locationSelect.value && dateSelect.value) refreshChart().catch(showError);
}, 60000);
function showError(error) { status.textContent = error.message; }
initialize();
</script>
</body>
</html>
"""


def configured_data_dir() -> Path:
    data_directory = "data"
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open(encoding="utf-8") as config_file:
                config = json.load(config_file)
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Unable to read {CONFIG_PATH}: {error}") from error
        if not isinstance(config, dict):
            raise RuntimeError(f"Configuration in {CONFIG_PATH} must be a JSON object.")
        data_directory = config.get("data_directory", data_directory)
    if not isinstance(data_directory, str) or not data_directory:
        raise RuntimeError("'data_directory' must be a non-empty string.")
    path = Path(data_directory)
    return path if path.is_absolute() else SCRIPT_DIR / path


def discover_data(data_dir: Path) -> dict[str, dict[str, Path]]:
    discovered: dict[str, dict[str, Path]] = {}
    if not data_dir.exists():
        return discovered
    for metric, (suffix, _, _) in METRICS.items():
        for directory in data_dir.glob(f"*{suffix}"):
            if directory.is_dir():
                location = directory.name[:-len(suffix)]
                discovered.setdefault(location, {})[metric] = directory
    return discovered


class DashboardHandler(BaseHTTPRequestHandler):
    data_dir: Path

    def respond(self, status_code: int, content_type: str, body: bytes) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def respond_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.respond(status_code, "application/json; charset=utf-8", body)

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        query = parse_qs(parsed_url.query)
        if parsed_url.path == "/":
            self.respond(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        elif parsed_url.path == "/api/options":
            self.handle_options(query)
        elif parsed_url.path == "/api/data":
            self.handle_data(query)
        else:
            self.respond_json(404, {"error": "Not found"})

    def handle_options(self, query: dict[str, list[str]]) -> None:
        discovered = discover_data(self.data_dir)
        locations = sorted(discovered)
        location = query.get("location", [locations[0] if locations else ""])[0]
        metric = query.get("metric", ["temperature"])[0]
        if metric not in METRICS:
            self.respond_json(400, {"error": "Unknown reading type"})
            return
        dates = []
        if location in discovered and metric in discovered[location]:
            dates = sorted(
                path.stem
                for path in discovered[location][metric].glob("*.csv")
                if path.is_file() and DATE_PATTERN.fullmatch(path.stem)
            )
        self.respond_json(200, {"locations": locations, "dates": dates})

    def handle_data(self, query: dict[str, list[str]]) -> None:
        location = query.get("location", [""])[0]
        metric = query.get("metric", [""])[0]
        selected_date = query.get("date", [""])[0]
        if metric not in METRICS:
            self.respond_json(400, {"error": "Unknown reading type"})
            return
        if not DATE_PATTERN.fullmatch(selected_date):
            self.respond_json(400, {"error": "Date must use YYYY-MM-DD format"})
            return
        try:
            date.fromisoformat(selected_date)
        except ValueError:
            self.respond_json(400, {"error": "Invalid date"})
            return

        data_dir = discover_data(self.data_dir)
        metric_dirs = data_dir.get(location, {})
        if metric not in metric_dirs:
            self.respond_json(404, {"error": "No data found for this location and reading type"})
            return
        data_path = metric_dirs[metric] / f"{selected_date}.csv"
        if not data_path.is_file():
            self.respond_json(404, {"error": "No readings found for this date"})
            return

        points = []
        try:
            with data_path.open(encoding="utf-8") as data_file:
                for line_number, line in enumerate(data_file, start=1):
                    time_text, separator, value_text = line.strip().partition(";")
                    if not separator:
                        raise ValueError(f"Expected time;value on line {line_number}")
                    try:
                        time_value = time_text
                        value = float(value_text)
                    except ValueError as error:
                        raise ValueError(f"Invalid reading on line {line_number}") from error
                    points.append({"time": time_value, "value": value})
        except (OSError, ValueError) as error:
            logging.exception("Unable to read sensor data from %s", data_path)
            self.respond_json(500, {"error": f"Unable to read sensor data: {error}"})
            return

        _, label, unit = METRICS[metric]
        self.respond_json(200, {
            "location": location,
            "label": label,
            "unit": unit,
            "date": selected_date,
            "points": points,
        })

    def log_message(self, format: str, *args: object) -> None:
        logging.info("%s - %s", self.address_string(), format % args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a browser dashboard for hygrometer CSV data.")
    parser.add_argument("--host", default="0.0.0.0", help="interface to listen on (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=6141, help="port to listen on (default: 6141)")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")

    DashboardHandler.data_dir = configured_data_dir()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logging.info("Serving dashboard at http://%s:%s/ using data in %s",
                 args.host, server.server_port, DashboardHandler.data_dir)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Stopping dashboard.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
