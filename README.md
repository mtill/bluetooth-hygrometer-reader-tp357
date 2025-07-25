# bluetooth-hygrometer-reader-tp357
this is a small experiment for receiving &amp; storing humidiy and temperature data from TP357 bluetooth low energy sensors

## dependencies
The python script depends on bleak: https://github.com/hbldh/bleak

## how to use
to start receiving and storing data, start the hum.py script:
<code>
./hum.py "E4:53:44:82:F6:AB" living-room \>/var/tmp/hum-living-room-err.log 2>&1 &
</code>

Replace E4:53:44:... with the ID of your tp357 sensor, and change "living-room" to the name of the location where this sensor is being placed.

This will store received data in the data directory.


