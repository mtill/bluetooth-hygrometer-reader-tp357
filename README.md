# bluetooth-hygrometer-reader-tp357
this is a small experiment for receiving &amp; storing humidiy and temperature data from TP357 bluetooth low energy sensors

## dependencies
The python script depends on bleak: https://github.com/hbldh/bleak

## how to use
to start receiving and storing data, start the hum.py script:
<code>
./hum.py \>/var/tmp/hum-living-room-err.log 2>&1 &
</code>

Copy `config.example.json` to `config.json`, then configure each sensor in the
`sensors` list with its Bluetooth address and a unique location name. The live
`config.json` is excluded from Git because it may contain credentials. Existing
single-sensor configurations using top-level `device_address` and `location`
continue to work; switch to the `sensors` list to add more devices.
The BLE UUIDs, command, and reconnect interval are fixed constants in
`hum.py`, rather than configurable values in `config.json`.

Each sensor runs as an independent asyncio task in the same process, with
separate CSV files and alert state. The top-level `critical` values are the
default uncritical ranges for all sensors. A sensor can independently override
either range in its own `critical` object: set `temperature_c`, `humidity_percent`,
or both. Any omitted per-sensor range inherits the corresponding default.
For example, a sensor with `"critical": {"temperature_c": [18, 28]}` uses the
default humidity range while applying its own temperature range. The example
config also shows a separate humidity override. Simultaneous Bluetooth
connections depend on the adapter and Bleak platform backend, so verify that
your hardware supports the number of sensors you configure.

This will store received data in the data directory.

## View temperature and humidity curves

Start the browser dashboard from this directory:

```bash
python3 dashboard.py
```

Then open <http://127.0.0.1:8000/> in your browser. Choose a sensor location,
temperature or humidity, and a date. The chart refreshes automatically every
minute and reads the CSV files in the configured `data_directory`. By default,
the dashboard listens only on this computer; use `--host` and `--port` to
change the listening address if needed.

### Start the dashboard automatically

Install it as a systemd user service:

```bash
mkdir -p ~/.config/systemd/user
ln -s "$PWD/dashboard.service" ~/.config/systemd/user/dashboard.service
systemctl --user daemon-reload
systemctl --user enable --now dashboard.service
```

For it to start at boot even when you are not logged in, enable lingering for
your user (administrator privileges may be required):

```bash
sudo loginctl enable-linger "$USER"
```

Check or stop the service with `systemctl --user status dashboard.service` or
`systemctl --user stop dashboard.service`. View its logs with
`journalctl --user -u dashboard.service -f`. The dashboard will be available at
<http://127.0.0.1:8000/> after the service starts.

## critical readings

The reader sends notifications using the server and topic configured under
`ntfy` in `config.json`. For token authentication, set `token`. For HTTP Basic
authentication, set both `username` and `password` instead; do not configure
both methods at once. Leave all authentication fields empty for a public topic.
To disable notifications, omit the `ntfy` section or leave its `server` or
`topic` empty.
Protect `config.json` with restrictive file permissions if it contains
credentials (for example, `chmod 600 config.json`).

Readings outside the configured inclusive temperature or humidity ranges are
critical. The reader sends a notification when a metric becomes critical and
another when it returns to its uncritical range. If both readings change state
together, one notification describes both changes. Set the default ranges in
the top-level `critical` section of `config.json` and add per-sensor overrides
where needed.
