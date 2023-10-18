# V19
# AutoGrow - A Hydroponics project 4-16-23
# A collaboration between @switty, @vetch and @ww
# Started from example code at for soil sensor mux operation A to D
# https://learn.adafruit.com/mcp3008-spi-adc/python-circuitpython
# Started from example code before for relay control via GPIO pin
# https://raspi.tv/2013/rpi-gpio-basics-5-setting-up-and-using-outputs-with-rpi-gpio
# Site for GPIO interrupt example code
# https://roboticsbackend.com/raspberry-pi-gpio-interrupts-tutorial/

# This Python script runs a water pump and valves

# V1 4-16-23    Initial development
# V2 4-18-23    Pump timer release
# V3 4-20-23    Adding Soil Sensors via thread
# V4 4-24-23    Adding pH Sensor
# V5 5-08-23    Fixed a couple of bugs related to pH reading, added TDS formula, corrected spelling mistake
# V6 5-11-23    Added timestamp to CSV logs
# V7 5-12-23    Separate times for diag, CSV and API logs.  Fully populate max soil sensors
# V8 5-14-23    More API logging, switch to disable pH meter
# V9 5-23-23    Add pump API call
# V10 5-29-23   Add pH balance routine, TDS enable flag, detect when TDS is not working
# V11 6-3-23    Add pH balance time limit to balance routine
# V12 6-7-23    Fixed logging bug related to no network connection and web api calls
# V13 6-15-23   Changing scripts to Scripts
# V14 6-16-23   Change pump API
# V15 8-21-23   Close web api, water refresh, separate pH and water cycle
# V16 8-24-23   Changed water valves to be an independent schedule
# V17 9-4-23    Detect sensor thread crash and auto restart, more logging on pH open fail
# V18 10-16-23  Adding support for remote api config and external disk config file 
# V19 10-18-23  Fix bug in pH balance code related to remote parms

# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT
#
# To run code install
# sudo pip3 install adafruit-circuitpython-mcp3xxx
# This is from above adafruit website
# Must turn on SPI via sudo raspi-config

import array
import copy
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
import AGconfig # Doing this to get access to global_pH variable
from AGconfig import *
from AGsensors import *

AGsys("Starting")
AGsys("Version: " + str(VERSION))
AGsys("Flow control sensor GPIO pin: " + str(FLOW_PIN_INPUT))
AGsys("Pump delay to prevent back pressure: " + str(PUMP_DELAY))
AGsys("Sensor DIAG delay: " + str(SENSOR_TIME_DIAG))
AGsys("Max number of soil sensors for the system: " + str(MAX_SOIL_SENSORS))
AGsys("Logging timer: " + str(LOGGING_TIMER))
AGsys("Max water valves: " + str(MAX_WATER_VALVES))
AGsys("Print to console: " + str(PRINT_TO_CONSOLE))
AGsys("pH down relay: " + str(PH_DOWN_RELAY))
AGsys("pH up relay: " + str(PH_UP_RELAY))
AGsys("AG system log: " + SYS)
AGsys("AG pump log: " + PUMP)
AGsys("AG sensor log: " + SENSORS)
AGsys("AG error log: " + ERROR)
AGsys("AG sensor json log: " + SENSOR_JSON_FILE)
AGsys("AG pump json log: " + PUMP_JSON_FILE)
AGsys("AG file parm file: " + FILE_PARMS)
AGsys("AG remote config url: " + REMOTE_CONFIG_URL)
AGsys("Turn on remote parms: " + str(REMOTE_PARMS))
AGsys("Remote parm interval: " + str(REMOTE_PARM_INTERVAL))
AGsys(".........................................")

AGsys("Default parms ----------------------------------")
write_json_to_log(run_parms)
AGsys("End default parms ------------------------------")

#write_parm_file()  #Uncomment to get a default parms file out to disk

######## Read in old parms from file, verify, apply as needed #########################################
file_parms = read_parm_file()
if (len(file_parms) > 0):
   AGsys("Checking file parms for runtime update")
   if (update_parms(file_parms)):
      AGsys("One or more runtime parms were updated from file")
      AGsys("Updated parms from file -----------------------")
      write_json_to_log(run_parms)
      AGsys("End updated parms from file -------------------")
   else:
      AGsys("No parms were qualified for update")
else:
   AGsys("No file parms to check")

############# Read initial remote parms #########################################
if (REMOTE_PARMS):
   AGsys("Getting remote parms from web api")
   remote_parms = read_remote_parms()
   old_remote_parms = copy.deepcopy(remote_parms) # keep copy of parms
   if (remote_parms != {} and len(remote_parms) > 0):
      AGsys("Received remote parms")
      if (update_parms(remote_parms[0])):
         AGsys("Parms updated, writing to file")
         write_parm_file()
         AGsys("New parms after remote update -----------------")
         write_json_to_log(run_parms)
         AGsys("End remote parm updates ----------------------")
      else:
         AGsys("No updated needed for remote parms")
   else:
      AGsys("No remote parms available")

#################################################################################################

# VALVES is capitalized since it was a constant in a prior config, it is now dynamic based on run_parms
# The VALVES list contains the water valve timeing information
# First value is time between valve watering and second value is the duration the valve is open
# If the valve is disabled, before parms are set to zero
VALVES = []
for a in range(MAX_WATER_VALVES):
   if (run_parms["valve" + str(a+1) + "_active"] == True):
      VALVES.append( [ run_parms["valve" + str(a+1) + "_time"], run_parms["valve" + str(a+1) + "_duration"] ] )
   else:
      VALVES.append( [0,0] )

AGsys("Water schedule in seconds, zero means valve disabled --------")
cnt = 1
for valve in VALVES:
   AGsys("Valve: " + str(cnt) + " Time: " + str(valve[0]) + " Duration: " + str(valve[1]))
   cnt = cnt + 1
AGsys("....................................")

def all_relays_off(): # Force all relays off - shutoff pump and valves
   cnt = 0
   for a in Relays:
      GPIO.setup(a,GPIO.OUT)
      GPIO.output(a,0)
      if (cnt == 0):
         time.sleep(PUMP_DELAY) # Make sure pump is off before turning off valves
      cnt = cnt + 1

def log_water_valve_status(): # Log status of pump and valves
   output = "Pump: "
   if (Relay_Status[0] == True):
      output = output + "On "
   else:
      output = output + "Off"
   cnt = 1
   for a in range(1,MAX_WATER_VALVES+1):
      output = output + "  V" + str(cnt) + ": "
      if (Relay_Status[a] == True):
         output = output + "On "
      else:
         output = output + "Off"
      cnt = cnt + 1
   output = output + "  Flow Meter: " + str(flow_count)
   AGlog(output,PUMP)

def relay_control():
   for i in range(0,len(Relay_Status)):
      if (Relay_Status[i]):
         GPIO.output(Relays[i],1)
      else:
         GPIO.output(Relays[i],0)

def water_refresh():
   global flow_count
   AGsys("Starting Water refresh cycle");
   AGlog("Starting Water refresh cycle ------ Flow = " + str(flow_count),PUMP)
   Relay_Status[0] = True # Turn on water pump
   APIpump(Relay_Status,flow_count)
   relay_control()
   log_water_valve_status()
   time.sleep(run_parms["water_refresh_cycle_length"])
   Relay_Status[0] = False # Turn off water pump
   APIpump(Relay_Status,flow_count)
   relay_control()
   log_water_valve_status()
   AGsys("Finished Water refresh cycle");
   AGlog("Finished Water refresh cycle ----- Flow = " + str(flow_count),PUMP)
   flow_count = 0

# Water cycle routine, run a single passed in valve  ##########################################
def run_water_cycle(valve_number):
   global flow_count
   AGsys("Starting Water Cycle Valve: " + str(valve_number + 1) + " Flow = " + str(flow_count))
   AGlog("Starting Water Cycle Valve: " + str(valve_number + 1) + " Flow = " + str(flow_count),PUMP)
   APIpump(Relay_Status,flow_count)

   flow_count = 0 # Reset flow count after logging start cycle to look for leaks during sleep

   Relay_Status[valve_number + 1] = True # Turn valve on, pump is zero, valves start at 1
   APIpump(Relay_Status, flow_count) # Before relay engage incase web api is delayed
   flow_count = 0
   relay_control()
   log_water_valve_status()
   time.sleep(PUMP_DELAY)

   Relay_Status[0] = True # Turn on water pump (Zero is pump relay)
   APIpump(Relay_Status, flow_count)
   relay_control()
   log_water_valve_status()
   time.sleep(VALVES[valve_number][1])

   Relay_Status[0] = False # Turn off water pump (Zero is pump relay)
   APIpump(Relay_Status, flow_count)
   relay_control()
   log_water_valve_status()
   time.sleep(PUMP_DELAY)

   Relay_Status[valve_number + 1] = False # Turn off valve
   relay_control()
   log_water_valve_status()
   APIpump(Relay_Status, flow_count) # After relay engage incase web api delay
   flow_count = 0
   time.sleep(PUMP_DELAY)

   AGsys("Water Cycle Complete - Flow = " + str(flow_count))
   AGlog("Water Cycle Complete - Flow = " + str(flow_count),PUMP)
   APIpump(Relay_Status, flow_count)
# End water cycle routine #####################################

# Adjust pH if needed #########################################
def adjust_pH():
   current_pH = AGconfig.global_pH # Storing to prevent reading change while doing auto pH correct

   # If you needed to force pH value to test
   #   current_pH = 3

   lower_pH = run_parms["ideal_ph"] - run_parms["ph_spread"]
   upper_pH = run_parms["ideal_ph"] + run_parms["ph_spread"]
   AGsys("Auto pH enabled, Current pH: " + str(current_pH) + ", Range goal (" + str(lower_pH) + " - " + str(upper_pH) + ")")

   if (current_pH < 2 or current_pH > 12): # Prevent some odd pH reading from impacting auto ajustment
      AGsys("pH reading is out of spec, no auto adjustment possible")
      AGlog("ERROR - pH reading is out of spec and auto balance enabled",ERROR)
   else:
      if (current_pH < lower_pH): # pH too low, make higher
         AGsys("Making pH higher")
         Relay_Status[PH_UP_RELAY] = True
         relay_control()
         time.sleep(run_parms["ph_valve_time"])
         Relay_Status[PH_UP_RELAY] = False
         relay_control()

      if (current_pH > upper_pH): # pH too high, make lower
         AGsys("Making pH lower")
         Relay_Status[PH_DOWN_RELAY] = True
         relay_control()
         time.sleep(run_parms["ph_valve_time"])
         Relay_Status[PH_DOWN_RELAY] = False
         relay_control()

   pH_time_limit = time.time() + run_parms["ph_balance_interval"]
   AGsys("pH auto adjustment routine complete")
# End adjust pH if needed #####################################

GPIO.setmode(GPIO.BCM)

#Relay GPIO pin setup
Relays = [5,6,13,16,19,20,21,26]
all_relays_off()
Relay_Status = [False,False,False,False,False,False,False,False] # Pi hat has eight relays

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

# Make sure pH sample bucket is full before starting sensor thread
water_refresh()

# Start sensor thread
sensor_thread = threading.Thread(target=sensors,daemon=True)
sensor_thread.start()

remote_parm_time_limit = time.time() + REMOTE_PARM_INTERVAL # This is the timer for accessing remote web api parms
pH_time_limit = time.time() + run_parms["ph_balance_interval"] # Time when the next pH auto cycle can run
water_refresh_time_limit = time.time() + run_parms["water_refresh_cycle"] # Time when the next water refresh cycle will run for pH  sensor
logging_timer = 0 # Controls when logs output for timing status

valve_timers = [] # Setup initial time numbers for valves
for valve in VALVES:
   valve_timers.append(valve[0] + time.time())

while(True): # Master loop for water cycle and pH rebalance

   if (run_parms["balance_ph"] and (pH_time_limit - time.time()) < 1): # pH balance routine
      valve_number = -1 # Must be -1 for logic below to work
      cnt = 0
      shortest_timer = -1 # This must be -1 for logic below
      for valve_time in valve_timers:
         if (VALVES[cnt][0] != 0 and (valve_time < shortest_timer or valve_number == -1)):
            shortest_timer = valve_time
            valve_number = cnt
         cnt = cnt + 1

      # Check and see if too close to a water cycle to adjust pH
      # shortest_timer == -1 if there are no valves enabled
      if (run_parms["ph_balance_water_limit"] <  shortest_timer - time.time() or shortest_timer == -1):
         adjust_pH()
         pH_time_limit = time.time() + run_parms["ph_balance_interval"] # Time when the next pH auto cycle can run
      else: # Water cycle too close, reschedule
         AGsys("Water cycle too close to run pH balance routine, reschedule!!!!!")
         AGsys("Limit: " + str(round((run_parms["ph_balance_water_limit"] / 60),1)) + " Next water cycle valve: "\
 + str(valve_number + 1) + " Time: " + str(round((shortest_timer - time.time())/60,1)))
         pH_time_limit = time.time() + run_parms["ph_balance_retry"]

   # If needed run valve water cycle if timer is up
   # Check all valves here
   cnt = 0
   for valve_time in valve_timers:
      if (valve_time < time.time()):
         if (VALVES[cnt][0] != 0): # Zero here means valve is disabled
            run_water_cycle(cnt)
         valve_timers[cnt] = time.time() + VALVES[cnt][0]
      cnt = cnt + 1

   if (remote_parm_time_limit < time.time()): # Remote parm update routine
      remoet_parm_time_limit = time.time() + REMOTE_PARM_INTERVAL
      if (REMOTE_PARMS):
         AGsys("Getting remote parms from web api")
         remote_parms = read_remote_parms()
         if (remote_parms != {} and len(remote_parms) > 0):
            AGsys("Received remote parms")
            if (old_remote_parms != remote_parms):
               old_remote_parms = copy.deepcopy(remote_parms) # Keep copy of parms, no need to check duplicate parms
               if (update_parms(remote_parms[0])):
                  AGsys("Parms updated, writing to file")
                  write_parm_file()
                  AGsys("New parms after remote update -----------------")
                  write_json_to_log(run_parms)
                  AGsys("End remote parm updates ----------------------")
                  AGsys("Exiting program for restart")
                  sys.exit(0)
               else:
                  AGsys("No updated needed for remote parms")
            else:
               AGsys("Old remote parms same as new parms no need to check")

         else:
            AGsys("No remote parms available")

   if (water_refresh_time_limit < time.time()):  # Water refresh routine
      water_refresh()
      water_refresh_time_limit = time.time() + run_parms["water_refresh_cycle"]

   if (logging_timer < time.time()): # Log time left before cycles in this code block
      log_string = "Cycle minutes left: refresh:"
      current_time = time.time()
      log_string = log_string + str(round((water_refresh_time_limit - current_time)/60,1))

      if (run_parms["balance_ph"]):
         log_string = log_string + " pH:" + str(round((pH_time_limit - current_time)/60,1))

      cnt = 0
      for valve_time in valve_timers:
         if (VALVES[cnt][0] != 0):
            log_string = log_string + " V:" + str(cnt + 1) + " T:" + str(round((valve_time - current_time)/60,1))
         cnt = cnt + 1

      AGsys(log_string)

      if (not sensor_thread.is_alive()):
         AGsys("Sensor Thread has crashed !!!!!!!!, Restarting.....")
         AGlog("ERROR:  Sensor Thread has crashed",ERROR)
         sensor_thread = threading.Thread(target=sensors,daemon=True) # Restart crashed sensor thread
         sensor_thread.start()

      logging_timer = time.time() + LOGGING_TIMER

   time.sleep(5) # Master sleep in loop, must be smaller than all other sleep values
