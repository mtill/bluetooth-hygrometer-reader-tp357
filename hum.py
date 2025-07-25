#!/usr/bin/env python3
# coding=utf-8


import os
import sys
import logging
logger = logging.getLogger(__name__)
import asyncio
import datetime
from bleak import BleakScanner, BleakClient


thepath = "data"
uuid_write = "00010203-0405-0607-0809-0a0b0c0d2b11"
uuid_read  = "00010203-0405-0607-0809-0a0b0c0d2b10"
cmd = b"\xa7\x00\x00\x00\x00\x7a"   # day
#cmd = b"\xa6\x00\x00\x00\x00\x6a"   #week
#cmd = b"\xa8\x00\x00\x00\x00\x8a"   #year
hum_delta = 1.0
temp_delta = 0.5
time_delta_seconds = 900

last_hum = None
last_hum_timestamp = 0
last_temp = None
last_temp_timestamp = 0
fin_evt = asyncio.Event()
files_datestr = None


def callback(sender, data):
    global logger, last_hum, last_hum_timestamp, last_temp, last_temp_timestamp, hum_delta, temp_delta, time_delta_seconds

    logger.debug(f"{sender}: {data}")
    temp = (data[3] + data[4] * 256) / 10
    humi = data[5]
    #battery = data[6]   # not sure!

    thedate = datetime.datetime.now()
    ts = thedate.timestamp()
    datestr = thedate.strftime("%Y-%m-%d")
    timestr = thedate.strftime("%H:%M:%S")

    logger.debug("temp: " + str(temp))
    logger.debug("hum: " + str(humi))

    if last_temp is None or ts - last_temp_timestamp >= time_delta_seconds or abs(last_temp - temp) >= temp_delta:
        with open(temp_path + "/" + datestr + ".csv", "a", buffering=1) as the_file:
            the_file.write(timestr + ";" + str(temp) + "\n")
        last_temp = temp
        last_temp_timestamp = ts
    if last_hum is None or ts - last_hum_timestamp >= time_delta_seconds or abs(last_hum - humi) >= hum_delta:
        with open(hum_path + "/" + datestr + ".csv", "a", buffering=1) as the_file:
            the_file.write(timestr + ";" + str(humi) + "\n")
        last_hum = humi
        last_hum_timestamp = ts
    #print(battery)


def handle_disconnect(_: BleakClient):
    global logger, fin_evt
    logger.info("disconnected.")
    fin_evt.set()


async def main(address):
    global logger, fin_evt, uuid_read, uuid_write, cmd

    while True:
        try:
            device = await BleakScanner.find_device_by_address(address)
            if device:
                async with BleakClient(device, disconnected_callback=handle_disconnect, pair=False) as client:
                    logger.info(f"{client.address} connected")

                    await client.start_notify(uuid_read, callback)
                    #await client.write_gatt_char(uuid_write, cmd, response=False)
                    #for s in client.services:
                    #    print(s.description)
                    #    for c in s.characteristics:
                    #        print(c)
                    #        print(c.properties)
                    #        print()
                    #    print()

                    await fin_evt.wait()
                    await client.stop_notify(uuid_read)

        except:
            logger.warning("something went wrong.")
        finally:
            fin_evt.clear()
            await asyncio.sleep(30)


address = sys.argv[1]
name = sys.argv[2]
logging.basicConfig(filename='/var/tmp/hum-' + name + '.log', level=logging.ERROR, style='{', format='{asctime} {levelname} {filename}:{lineno}: {message}', datefmt='%Y-%m-%d %H:%M:%S')
hum_path = thepath + "/" + name.replace("/", "_") + "_humidity"
temp_path = thepath + "/" + name.replace("/", "_") + "_temperature"
os.makedirs(hum_path, exist_ok=True)
os.makedirs(temp_path, exist_ok=True)
asyncio.run(main(address))


