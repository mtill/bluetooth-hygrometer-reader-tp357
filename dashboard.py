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
CONFIG_PATH = SCRIPT_DIR / "dashboard-config.json"
STATIC_ASSETS = {
    "/static/dashboard.css": (SCRIPT_DIR / "static" / "dashboard.css", "text/css; charset=utf-8"),
    "/static/dashboard.js": (SCRIPT_DIR / "static" / "dashboard.js", "text/javascript; charset=utf-8"),
    "/": (SCRIPT_DIR / "static" / "index.html", "text/html; charset=utf-8"),
}
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
COLOR_PATTERN = re.compile(r"#[0-9a-fA-F]{6}\Z")
METRICS = {
    "temperature": ("_temperature", "Temperature", "°C"),
    "humidity": ("_humidity", "Humidity", "%"),
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        with CONFIG_PATH.open(encoding="utf-8") as config_file:
            config = json.load(config_file)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Unable to read {CONFIG_PATH}: {error}") from error
    if not isinstance(config, dict):
        raise RuntimeError(f"Configuration in {CONFIG_PATH} must be a JSON object.")
    return config


def configured_data_dir() -> Path:
    data_directory = load_config().get("data_directory", "data")
    if not isinstance(data_directory, str) or not data_directory:
        raise RuntimeError("'data_directory' must be a non-empty string.")
    path = Path(data_directory)
    return path if path.is_absolute() else SCRIPT_DIR / path


def configured_sensor_colors() -> dict[str, str]:
    sensor_colors = load_config().get("sensor_colors", {})
    if not isinstance(sensor_colors, dict):
        raise RuntimeError("'sensor_colors' must be an object mapping sensor locations to hex colors.")
    for location, color in sensor_colors.items():
        if not isinstance(location, str) or not location:
            raise RuntimeError("Sensor color locations must be non-empty strings.")
        if not isinstance(color, str) or not COLOR_PATTERN.fullmatch(color):
            raise RuntimeError(f"Color for sensor '{location}' must use #RRGGBB format.")
    return sensor_colors


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
    sensor_colors: dict[str, str]

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

    def respond_static(self, path: str) -> None:
        asset = STATIC_ASSETS.get(path)
        if asset is None:
            self.respond_json(404, {"error": "Not found"})
            return
        file_path, content_type = asset
        try:
            body = file_path.read_bytes()
        except OSError as error:
            logging.exception("Unable to read dashboard asset %s", file_path)
            self.respond_json(500, {"error": f"Unable to read dashboard asset: {error}"})
            return
        self.respond(200, content_type, body)

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        query = parse_qs(parsed_url.query)
        if parsed_url.path in STATIC_ASSETS:
            self.respond_static(parsed_url.path)
        elif parsed_url.path == "/api/options":
            self.handle_options(query)
        elif parsed_url.path == "/api/data":
            self.handle_data(query)
        else:
            self.respond_json(404, {"error": "Not found"})

    def handle_options(self, query: dict[str, list[str]]) -> None:
        discovered = discover_data(self.data_dir)
        metric = query.get("metric", ["temperature"])[0]
        if metric not in METRICS:
            self.respond_json(400, {"error": "Unknown reading type"})
            return
        dates = {
            path.stem
            for metric_dirs in discovered.values()
            if metric in metric_dirs
            for path in metric_dirs[metric].glob("*.csv")
            if path.is_file() and DATE_PATTERN.fullmatch(path.stem)
        }
        self.respond_json(200, {
            "dates": sorted(dates),
            "locations": sorted(discovered),
            "sensorColors": self.sensor_colors,
        })

    def handle_data(self, query: dict[str, list[str]]) -> None:
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
        series = []
        for location, metric_dirs in sorted(data_dir.items()):
            if metric not in metric_dirs:
                continue
            data_path = metric_dirs[metric] / f"{selected_date}.csv"
            if not data_path.is_file():
                continue

            points = []
            try:
                with data_path.open(encoding="utf-8") as data_file:
                    for line_number, line in enumerate(data_file, start=1):
                        time_text, separator, value_text = line.strip().partition(";")
                        if not separator:
                            raise ValueError(f"Expected time;value on line {line_number}")
                        try:
                            value = float(value_text)
                            hours, minutes, seconds = (int(part) for part in time_text.split(":"))
                            if hours > 23 or minutes > 59 or seconds > 59:
                                raise ValueError
                        except ValueError as error:
                            raise ValueError(f"Invalid reading on line {line_number}") from error
                        points.append({
                            "time": time_text,
                            "timeSeconds": hours * 3600 + minutes * 60 + seconds,
                            "value": value,
                        })
            except (OSError, ValueError) as error:
                logging.exception("Unable to read sensor data from %s", data_path)
                self.respond_json(500, {"error": f"Unable to read sensor data: {error}"})
                return
            if points:
                series.append({"location": location, "points": points})

        _, label, unit = METRICS[metric]
        self.respond_json(200, {
            "label": label,
            "unit": unit,
            "date": selected_date,
            "sensorCount": len(series),
            "readingCount": sum(len(item["points"]) for item in series),
            "series": series,
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
    DashboardHandler.sensor_colors = configured_sensor_colors()
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
