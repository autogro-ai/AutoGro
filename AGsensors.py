# Sensor package for AutoGrow
# V21

# TDS calculation adapted from Arduino sample at:
# https://wiki.keyestudio.com/KS0429_keyestudio_TDS_Meter_V1.0

# MCP3008 AtoD example from here
# https://learn.adafruit.com/mcp3008-spi-adc/python-circuitpython
# This site indicates what python libs to install etc

import sys
import os
import time
from AGconfig import *
import AGconfig # Used to gain access to global_pH
import busio
import board
import digitalio
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn

# Map function from:
# https://www.theamplituhedron.com/articles/How-to-replicate-the-Arduino-map-function-in-Python-for-Raspberry-Pi/
#  Prominent Arduino map function :)
def _map(x, in_min, in_max, out_min, out_max):
    return int((x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)

# get pH and return to main program, inserted for error recovery, USB reset
# This calls get_pH_driver where the work is done, this is only error recovery
def get_pH():
   driver_pH = get_pH_driver()
   if (driver_pH != -1):
      return driver_pH
   driver_pH = get_pH_driver() # Trying get pH twice due to boot time problem
   if (driver_pH != -1):
      return driver_pH

   if (get_pH.usb_reset_time == 0 or (get_pH.usb_reset_time + 1200) < time.time()): # Just allow usb reset once in 20 minutes (1200 is seconds in 20 minutes)
      AGlog("Resetting USB bus!!!!!",ERROR)
      AGlog("Resetting USB bus!!!!!",SENSORS)
      get_pH.usb_reset_time = time.time()
      os.system(USB_RESET) # Rest USB bus and try pH again
      time.sleep(3)
      return get_pH_driver()
   else:
      return -1
get_pH.usb_reset_time = 0 # This is used as a static variable substitute in above function


# get_pH_driver() reads the USB serial port and gets pH from probe #######################
def get_pH_driver():
   try:
      ser = serial.Serial(run_parms["ph_sensor_port"],9600,timeout = 4)
   except Exception as e:
      AGlog("ERROR - Could not open USB port with pH probe: " + str(e),ERROR)
      return -1

   time_out = False
   parse_error = False
   pH_mismatch = False
   parse_error_string = ""
   previous_pH = 0
   stored_previous_pH = False
   end_time = time.time() + 20

   while (end_time > time.time()):
      line = ""
      s = ""
      while(line != b"\r" and end_time > time.time()):
         line = ser.readline(1)
         if (line == b""):
            time_out = True
            continue
         s = s + line.decode()

      try:
         pH_value = float(s) # Attempt to convert pH string to float, if error read USB again
         float_convert_success = True
      except Exception:
         parse_error = True
         parse_error_string = s
         continue

      if (stored_previous_pH == False):
         previous_pH = pH_value
         stored_previous_pH = True
      else:
         if ( abs(previous_pH - pH_value) < .1): # Previous two pH values are close, good to return
            break
         else:
            previous_pH = pH_value
            pH_mismatch = True

   # Close USB serial port
   try:
      ser.close()
   except Exception:
      AGlog("ERROR - Could not close USB serial port",ERROR)

   if (time_out == True):
      AGlog("WARNING - pH routine received a time out",ERROR)

   if (parse_error == True):
      AGlog("WARNING - pH routine got a parse error: " + parse_error_string,ERROR)

   if (pH_mismatch == True):
      AGlog("WARNING - pH routine received a pH mismatch",ERROR)

   if (end_time > time.time()):
      return pH_value
   else:
      AGlog("ERROR - pH routine received a global time out, no pH reading",ERROR)
      return -1

# Begin main sensor thread ##############################################

def sensors():
   # Store last good ph reading time - used for caching incase of pH error
   last_good_pH_time = 0
   # create the spi bus
   spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
   # create the cs (chip select)
   cs = digitalio.DigitalInOut(board.D17)
   # create the mcp object
   mcp = MCP.MCP3008(spi,cs)
   # Setup array to hold MCP objects
   SoilArray = []
   # create analog input channels
   for i in range(0,run_parms["number_of_soil_sensors"]):
      SoilArray.append(AnalogIn(mcp,i)) # i is the input pin on the mux

   wq = AnalogIn(mcp,7) # Water qaulity sensor is connected to last mux input - #7
   # wq.voltage is actual voltage measurement, same as volt meter

   # Setup array to hole raw soil sensor values
   SoilRaw = [None] * run_parms["number_of_soil_sensors"]
   # Setup array to hold soil percent wet values
   SoilPercent = [None] * run_parms["number_of_soil_sensors"]

   sensor_time_api_clock = 0  # Stores clock to trigger API web call
   sensor_time_diag_clock = 0 # Stores clock to trigger DIAG log call

   while(True):

      if (run_parms["ph_sensor_enabled"]):
         pH = get_pH() # Call time for this function can be lengthy if pH probe is having trouble, look at error log
         if (pH != -1):
            AGconfig.global_pH = pH # Set system wide pH value for possible auto adjustment
            last_good_pH_time = time.time()
         else:
            # Thinking through initial run with last_good_ph_time = 0, the logic still works
            if ((last_good_pH_time + 1500) > time.time()): # Use old pH value for 25 minutes if pH system is offline (1500 seconds is 25 minutes)
               AGlog("Using cached pH reading",SENSORS)
               # Don't update pH value just use old one unless too old
            else:
               AGconfig.global_pH = -1
      else:
         pH = -1 # Since pH meter is not enabled just set to -1, same as an error


      # TDS routine ###############################################
      if (run_parms["enable_tds_meter"]):
         # TDS water quality calc from Arduino example
         # Note: cannot determine if TDS is not plugged in based on zero since this is a valid value
         tds_average = 0
         TDS_FAULT = False # Set if TDS fault detected
         for i in range (0,run_parms["tds_samples"]):
            time.sleep(.1) # Time between TDS samples
            wq_voltage =  wq.voltage # Real voltage from TDS
            temperatureCompensation = 1.0 + .02 * (run_parms["room_temperature"] - 25)
            voltageCompensation = wq_voltage / temperatureCompensation
            tdsValue = ((133.42 * voltageCompensation * voltageCompensation * voltageCompensation) - 255.86 * voltageCompensation * voltageCompensation + 857.39 * voltageCompensation) * .5
            if (tdsValue == 0): # Zero from the TDS sensor is considered an error condition
               TDS_FAULT = True
            tds_average = tds_average + tdsValue

         if (TDS_FAULT == True):
            AGlog("ERROR - TDS fault",ERROR)
            tdsValue = -1
         else:
            tdsValue = round(tds_average / TDS_SAMPLES,1) # Ending TDS value is an average of readings

      else:
         tdsValue = -1 # if TDS is not enabled, same as error but no error logging
      # End TDS routine #############################################

      for i in range(0,run_parms["number_of_soil_sensors"]):
         SoilRaw[i] = SoilArray[i].value
         SoilPercent[i] = _map(SoilRaw[i],run_parms["soil_wet"],run_parms["soil_dry"],100,0)
         if (SoilPercent[i] < 0): # Force Soil Percent to 0 or 100 if above or below
            SoilPercent[i] = 0
         if (SoilPercent[i] > 100):
            SoilPercent[i] = 100

         if (SoilRaw[i] == 0): # If the soil sensor is unplugged, the AtoD returns 0, so flagging this as -1
            SoilPercent[i] = -1
            SoilRaw[i] = -1
            AGlog("Possible disconnected soil sensor: " + str(i),ERROR)

      # Prepping buf string for regular diag log, just soil sensors that are active
      # Yes, prepping these on every loop even though they are just used once in a while
      buf = ""
      for i in range(0,run_parms["number_of_soil_sensors"]):
         buf = buf + "S" + str(i) + ": " + str(SoilRaw[i]) + " (" + str(SoilPercent[i]) + ") "

      buf = buf + "WC: " + str(tdsValue) # WC is water quality sensor
      buf = buf + " pH: " + str(AGconfig.global_pH) # pH from USB probe


      # Prepping SensorAPI list for web API call
      # The list will contain all possible max soil sensors with ones not in use ""
      # This is being done for the web API so DBs can populate all their columns
      SensorAPI = []
      for i in range (0,MAX_SOIL_SENSORS):
         if (i < run_parms["number_of_soil_sensors"]):
            SensorAPI.append(SoilPercent[i])
         else:
            SensorAPI.append("")  # Forcing full Soil Sensor List for DB purposes, ones not in use get ""

      SensorAPI.append(tdsValue)
      SensorAPI.append(AGconfig.global_pH)

      ###### Decide here what to log based on time delay counts - all logging funcs can have different log times
      current_clock = time.time()

      if (sensor_time_diag_clock < current_clock): # DIAG log block
         AGlog(str(buf),SENSORS)
         sensor_time_diag_clock = current_clock + SENSOR_TIME_DIAG

      if (sensor_time_api_clock < current_clock): # API web call block, note SensorCSV is used same as CSVlog
         APIsensor(SensorAPI)
         sensor_time_api_clock = current_clock + run_parms["sensor_time_api"]

      time.sleep(3) # Time delay on master sensor loop, must be smaller than smallest logging delay
