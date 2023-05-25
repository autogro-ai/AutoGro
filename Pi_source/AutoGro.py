# V9
# AutoGrow - A Hydroponics project 4-16-23
# A collaboration between @switty, @vetch and @ww
# Started from example code at for soil sensor mux operation A to D
# https://learn.adafruit.com/mcp3008-spi-adc/python-circuitpython
# Started from example code before for relay control via GPIO pin
# https://raspi.tv/2013/rpi-gpio-basics-5-setting-up-and-using-outputs-with-rpi-gpio
# Site for GPIO interrupt example code
# https://roboticsbackend.com/raspberry-pi-gpio-interrupts-tutorial/

# This Python script runs a water pump and valves

# V1 4-16-23  Initial development
# V2 4-18-23  Pump timer release
# V3 4-20-23  Adding Soil Sensors via thread
# V4 4-24-23  Adding pH Sensor
# V5 5-08-23  Fixed a couple of bugs related to pH reading, added TDS formula, corrected spelling mistake
# V6 5-11-23  Added timestamp to CSV logs
# V7 5-12-23  Separate times for diag, CSV and API logs.  Fully populate max soil sensors
# V8 5-14-23  More API logging, switch to disable pH meter
# V9 5-23-23  Add pump API call

# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT
#
# To run code install
# sudo pip3 install adafruit-circuitpython-mcp3xxx
# This is from above adafruit website
# Must turn on SPI via sudo raspi-config

import array
import time
import busio
import digitalio
import board
import RPi.GPIO as GPIO
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn
from datetime import datetime
import signal
import sys
import csv
import threading
from AGconfig import *
from AGsensors import *

AGsys("Starting")
AGsys("Version " + str(VERSION))
AGsys("Flow control sensor GPIO pin " + str(FLOW_PIN_INPUT))
AGsys("Number of water valves " + str(NUM_WATER_VALVES))
AGsys("Water cycle length per valve " + str(WATER_CYCLE_LENGTH))
AGsys("Pump delay to prevent back pressure " + str(PUMP_DELAY))
AGsys("Time between water cycles " + str(WATER_CYCLE_TIME))
AGsys("Sensor API delay " + str(SENSOR_TIME_API))
AGsys("Sensor CSV delay " + str(SENSOR_TIME_CSV))
AGsys("Sensor DIAG delay " + str(SENSOR_TIME_DIAG))
AGsys("Soil raw value wet " + str(SOIL_WET))
AGsys("Soil raw value dry " + str(SOIL_DRY))
AGsys("Number of soil sensors " + str(NUM_SOIL_SENSORS))
AGsys("Max number of soil sensors for the system " + str(MAX_SOIL_SENSORS))
AGsys("pH sensor USB port " + USB_PORT)
AGsys("pH sensor enabled " + str(PH_ENABLED))
AGsys("Room temperature in Celsius " + str(ROOM_TEMPERATURE))
AGsys("SENSOR URL API endpoint " + SENSOR_URL)
AGsys("PUMP URL API endpoint " + PUMP_URL)
AGsys("Enable web API " + str(WEB_API))
AGsys(".........................................")

def all_relays_off(): # Force all relays off - shutoff pump and valves
   cnt = 0
   for a in Relays:
      GPIO.setup(a,GPIO.OUT)
      GPIO.output(a,0)
      if (cnt == 0):
         time.sleep(PUMP_DELAY) # Make sure pump is off before turning off valves
      cnt = cnt + 1

def log_relay_status(): # Log status of pump and valves
   output = "Pump: "
   if (Relay_Status[0] == True):
      output = output + "On "
   else:
      output = output + "Off"
   cnt = 1
   for a in range(1,NUM_WATER_VALVES+1):
      output = output + "  V" + str(cnt) + ": "
      if (Relay_Status[a] == True):
         output = output + "On "
      else:
         output = output + "Off"
      cnt = cnt + 1
   output = output + "  Flow Meter: " + str(flow_count)
   AGlog(output,PUMP)

def engage_relays():
   for a in range(0,NUM_WATER_VALVES+1):
      if (Relay_Status[a] == True):
         GPIO.output(Relays[a],1)
      else:
         GPIO.output(Relays[a],0)

GPIO.setmode(GPIO.BCM)

#Relay GPIO pin setup
Relays = [5,6,13,16,19,20,21,26]
all_relays_off()
Relay_Status = [False,False,False,False,False,False,False,False]

flow_count = 0  # used to store total flow count
# routine for flow meter pin interrupt
def flow_meter_trigger(channel):
   global flow_count
   flow_count = flow_count + 1

# setup Flow meter input pin - 25
GPIO.setup(FLOW_PIN_INPUT,GPIO.IN,pull_up_down=GPIO.PUD_DOWN)
GPIO.add_event_detect(FLOW_PIN_INPUT,GPIO.FALLING,callback=flow_meter_trigger,bouncetime=5)

# Catch ctrl-c and turn off pump before exit
def signal_handler(sig,frame):
   all_relays_off()
   AGsys("Program exit")
   sys.exit(0)

# Install signal handler for ctrl-c
signal.signal(signal.SIGINT,signal_handler)
signal.signal(signal.SIGTERM,signal_handler)

# Start sensor thread
threading.Thread(target=sensors,daemon=True).start()

while(True):
   AGsys("Starting Water Cycle - Flow = " + str(flow_count))
   AGlog("Starting Water Cycle -------- Flow = " + str(flow_count),PUMP)
   CSVlog(["Start_Water_Cycle",flow_count],CSV_PUMP)
   APIpump("Starting Water Cycle",flow_count)

   flow_count = 0 # Reset flow count after logging start cycle to look for leaks during sleep
   total_flow_count = 0 # total_flow_count is keeping track of all flow count for complete water cycle, flow_count is per valve
   log_relay_status()
   engage_relays()
   for a in range (1,NUM_WATER_VALVES+1):
      Relay_Status[a] = True # Turn on valve
      log_relay_status()
      APIpump("Valve " + str(a) + " ON", flow_count) # Before relay engage incase web api delay
      total_flow_count =  total_flow_count + flow_count
      flow_count = 0
      engage_relays()
      time.sleep(PUMP_DELAY)
      Relay_Status[0] = True # Turn on water pump (Zero is pump relay)
      log_relay_status()
      engage_relays()
      time.sleep(WATER_CYCLE_LENGTH)
      Relay_Status[0] =  False # Turn off water pump (Zero is pump relay)
      log_relay_status()
      engage_relays()
      time.sleep(PUMP_DELAY)
      Relay_Status[a] = False # Turn off valve
      log_relay_status()
      engage_relays()
      APIpump("Valve " + str(a) + " OFF", flow_count) # After relay engage incase web api delay
      total_flow_count = total_flow_count + flow_count
      flow_count = 0
      time.sleep(PUMP_DELAY)
   AGsys("Water Cycle Complete - Flow = " + str(total_flow_count))
   AGlog("Water Cycle Complete ------- Flow = " + str(total_flow_count),PUMP)
   CSVlog(["End_Water_Cycle",total_flow_count],CSV_PUMP)
   APIpump("End Water Cycle",total_flow_count)

   ###### Sleep until next water cycle ######
   sleep_finish_time = time.time() + WATER_CYCLE_TIME

   while (sleep_finish_time > time.time()):
      AGsys("Sleeping until next water cycle - Seconds left: " + str(round(sleep_finish_time - time.time())))
      if (sleep_finish_time - time.time() > 120):
         time.sleep(60)
      else:
         time.sleep(5)