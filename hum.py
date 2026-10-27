#!/usr/bin/env python3
# coding=utf-8

import asyncio
import base64
import datetime
import json
import logging
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from bleak import BleakClient, BleakScanner


logger = logging.getLogger(__name__)
script_dir = Path(__file__).resolve().parent
config_path = script_dir / "config.json"

UUID_WRITE = "00010203-0405-0607-0809-0a0b0c0d2b11"
UUID_READ = "00010203-0405-0607-0809-0a0b0c0d2b10"
COMMAND_HEX = "a7000000007a"
RECONNECT_SECONDS = 30


def load_config():
    with config_path.open(encoding="utf-8") as config_file:
        loaded_config = json.load(config_file)

    ntfy = loaded_config.get("ntfy") or {}
    token = ntfy.get("token", "")
    username = ntfy.get("username", "")
    password = ntfy.get("password", "")
    if token and (username or password):
        raise ValueError("Configure either ntfy token or username/password, not both")
    if bool(username) != bool(password):
        raise ValueError("Configure both ntfy username and password")
    return loaded_config


config = load_config()


def publish_ntfy(title, message):
    ntfy = config.get("ntfy") or {}
    server = ntfy.get("server")
    topic = ntfy.get("topic")
    if not server or not topic:
        return

    url = server.rstrip("/") + "/" + quote(topic, safe="")
    headers = {"Title": title}
    if ntfy.get("token"):
        headers["Authorization"] = "Bearer " + ntfy["token"]
    elif ntfy.get("username"):
        credentials = f'{ntfy["username"]}:{ntfy["password"]}'.encode("utf-8")
        headers["Authorization"] = "Basic " + base64.b64encode(credentials).decode("ascii")
    request = Request(url, data=message.encode("utf-8"), headers=headers, method="POST")
    with urlopen(request, timeout=10):
        pass


async def send_ntfy_notification(title, message):
    try:
        await asyncio.to_thread(publish_ntfy, title, message)
    except (URLError, TimeoutError, OSError):
        logger.exception("Failed to send ntfy notification")


def configured_sensors():
    if "sensors" in config:
        sensors = config["sensors"]
    else:
        sensors = [{
            "device_address": config["device_address"],
            "location": config["location"],
        }]

    if not sensors:
        raise ValueError("Configure at least one sensor")

    addresses = [sensor["device_address"] for sensor in sensors]
    safe_locations = [sensor["location"].replace("/", "_") for sensor in sensors]
    if len(set(addresses)) != len(addresses):
        raise ValueError("Each sensor must have a unique device_address")
    if len(set(safe_locations)) != len(safe_locations):
        raise ValueError("Each sensor must have a unique location")
    return sensors


class SensorMonitor:
    def __init__(self, sensor):
        self.sensor = sensor
        self.location = sensor["location"]
        safe_location = self.location.replace("/", "_")
        data_dir = Path(config["data_directory"])
        if not data_dir.is_absolute():
            data_dir = script_dir / data_dir
        self.hum_path = data_dir / (safe_location + "_humidity")
        self.temp_path = data_dir / (safe_location + "_temperature")
        self.hum_path.mkdir(parents=True, exist_ok=True)
        self.temp_path.mkdir(parents=True, exist_ok=True)

        self.last_hum = None
        self.last_hum_timestamp = 0
        self.last_temp = None
        self.last_temp_timestamp = 0
        self.critical_metrics_state = set()
        self.disconnected = asyncio.Event()
        self.loop = asyncio.get_running_loop()

    def callback(self, sender, data):
        logger.debug("%s (%s): %s", self.location, sender, data)
        temp = (data[3] + data[4] * 256) / 10
        humi = data[5]

        now = datetime.datetime.now()
        timestamp = now.timestamp()
        datestr = now.strftime("%Y-%m-%d")
        timestr = now.strftime("%H:%M:%S")

        logger.debug("%s temperature: %s", self.location, temp)
        logger.debug("%s humidity: %s", self.location, humi)

        storage = config["storage"]
        time_delta_seconds = storage["time_delta_seconds"]
        if (
            self.last_temp is None
            or timestamp - self.last_temp_timestamp >= time_delta_seconds
            or abs(self.last_temp - temp) >= storage["temperature_delta"]
        ):
            with (self.temp_path / (datestr + ".csv")).open("a", buffering=1) as data_file:
                data_file.write(timestr + ";" + str(temp) + "\n")
            self.last_temp = temp
            self.last_temp_timestamp = timestamp
        if (
            self.last_hum is None
            or timestamp - self.last_hum_timestamp >= time_delta_seconds
            or abs(self.last_hum - humi) >= storage["humidity_delta"]
        ):
            with (self.hum_path / (datestr + ".csv")).open("a", buffering=1) as data_file:
                data_file.write(timestr + ";" + str(humi) + "\n")
            self.last_hum = humi
            self.last_hum_timestamp = timestamp

        default_ranges = config["critical"]
        sensor_ranges = self.sensor.get("critical", {})
        temperature_range = sensor_ranges.get(
            "temperature_c",
            default_ranges["temperature_c"],
        )
        humidity_range = sensor_ranges.get(
            "humidity_percent",
            default_ranges["humidity_percent"],
        )
        critical_metrics = set()
        if not temperature_range[0] <= temp <= temperature_range[1]:
            critical_metrics.add("temperature")
        if not humidity_range[0] <= humi <= humidity_range[1]:
            critical_metrics.add("humidity")

        newly_critical = critical_metrics - self.critical_metrics_state
        newly_uncritical = self.critical_metrics_state - critical_metrics
        if newly_critical or newly_uncritical:
            statuses = []
            if newly_critical:
                statuses.append("Critical: " + ", ".join(sorted(newly_critical)))
            if newly_uncritical:
                statuses.append("Back in range: " + ", ".join(sorted(newly_uncritical)))
            if newly_critical and newly_uncritical:
                status_title = "Hygrometer status changed"
            elif newly_critical:
                status_title = "Hygrometer critical"
            else:
                status_title = "Hygrometer recovered"
            title = f"{self.location}: {status_title}"
            message = (
                f"{'; '.join(statuses)}. Current: "
                f"temperature {temp}°C, humidity {humi}%"
            )
            self.loop.create_task(send_ntfy_notification(title, message))
        self.critical_metrics_state = critical_metrics

    def handle_disconnect(self, _: BleakClient):
        logger.info("%s disconnected.", self.location)
        self.disconnected.set()

    async def run(self):
        while True:
            try:
                device = await BleakScanner.find_device_by_address(self.sensor["device_address"])
                if device:
                    async with BleakClient(
                        device,
                        disconnected_callback=self.handle_disconnect,
                        pair=False,
                    ) as client:
                        logger.info("%s connected", client.address)
                        await client.start_notify(UUID_READ, self.callback)
                        await self.disconnected.wait()
                        await client.stop_notify(UUID_READ)
            except Exception:
                logger.exception("Sensor worker failed for %s", self.location)
            finally:
                self.disconnected.clear()
                await asyncio.sleep(RECONNECT_SECONDS)


async def main():
    sensors = configured_sensors()
    monitors = [SensorMonitor(sensor) for sensor in sensors]
    await asyncio.gather(*(monitor.run() for monitor in monitors))


sensor_configs = configured_sensors()
logging_config = config["logging"]
logging.basicConfig(
    filename=logging_config["file"].format(
        location=sensor_configs[0]["location"].replace("/", "_")
        if len(sensor_configs) == 1
        else "all-sensors"
    ),
    level=getattr(logging, logging_config["level"].upper()),
    style="{",
    format="{asctime} {levelname} {filename}:{lineno}: {message}",
    datefmt="%Y-%m-%d %H:%M:%S",
)
asyncio.run(main())
