# Sensor package for AutoGrow

# Versions
# V5 - fixed bugs in pH readings, added TDS formula

# TDS calcuation adapted from Arduino sample at:
# https://wiki.keyestudio.com/KS0429_keyestudio_TDS_Meter_V1.0

# MCP3008 AtoD example from here
# https://learn.adafruit.com/mcp3008-spi-adc/python-circuitpython
# This site indicates what pythom libs to install etc

import sys
import time
from AGconfig import *
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

# get_pH() reads the USB serial port and gets pH from probe #######################
def get_pH():
   try:
      ser = serial.Serial(USB_PORT,9600,timeout = 4)
   except Exception:
      AGlog("ERROR - Could not open USB port with pH probe",ERROR)
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

   if (time_out == True):
      AGlog("WARNING - pH routine received a time out",ERROR)

   if (parse_error == True):
      AGlog("WARNING - pH routine got a parse error: " + parse_error_string,ERROR)

   if (pH_mismatch == True):
      AGlog("WARNING - pH routine received a pH mismatch",ERROR)

   if (end_time > time.time()):
      return pH_value
   else:
      AGlog("ERROR - pH routine received a global timout, no pH reading",ERROR)
      return -1

# Begin main sensor thread ##############################################

def sensors():
   # create the spi bus
   spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
   # create the cs (chip select)
   cs = digitalio.DigitalInOut(board.D17)
   # create the mcp object
   mcp = MCP.MCP3008(spi,cs)
   # Setup array to hold MCP objects
   SoilArray = []
   # create analog input channels
   for i in range(0,NUM_SOIL_SENSORS):
      SoilArray.append(AnalogIn(mcp,i)) # i is the input pin on the mux

   wq = AnalogIn(mcp,7) # Water qaulity sensor is connected to last mux input - #7
   # wq.voltage is actual voltage measurement, same as volt meter

   # Setup array to hole raw soil sensor values
   SoilRaw = [None] * NUM_SOIL_SENSORS
   # Setup array to hold soil percent wet values
   SoilPercent = [None] * NUM_SOIL_SENSORS

   while(True):
      pH = get_pH()

      # TDS water quality calc from Arduino example
      wq_voltage =  wq.voltage # Real voltage from TDS
      temperatureCompensation = 1.0 + .02 * (ROOM_TEMPERATURE - 25)
      voltageCompensation = wq_voltage / temperatureCompensation
      tdsValue = ((133.42 * voltageCompensation * voltageCompensation * voltageCompensation) - 255.86 * voltageCompensation * voltageCompensation + 857.39 * voltageCompensation) * .5
      tdsValue = round(tdsValue,1)

      for i in range(0,NUM_SOIL_SENSORS):
         SoilRaw[i] = SoilArray[i].value
         SoilPercent[i] = _map(SoilRaw[i],SOIL_WET,SOIL_DRY,100,0)
         if (SoilPercent[i] < 0): # Force Soil Percent to 0 or 100 if above or below
            SoilPercent[i] = 0
         if (SoilPercent[i] > 100):
            SoilPercent[i] = 100

         if (SoilRaw[i] == 0): # If the soil sensor is unplugged, the AtoD returns 0, so flagging this as -1
            SoilPercent[i] = -1
            SoilRaw[i] = -1
            AGlog("Possible disconnected soil sensor: " + str(i),ERROR)

      buf = ""
      for i in range(0,NUM_SOIL_SENSORS):
         buf = buf + "S" + str(i) + ": " + str(SoilRaw[i]) + " (" + str(SoilPercent[i]) + ") "

      buf = buf + "WC: " + str(tdsValue) # WC is water quaility sensor
      buf = buf + " pH: " + str(pH) # pH from USB probe

      SensorCSV = [] # Putting data in list for CSV call
      for i in range (0,NUM_SOIL_SENSORS):
         SensorCSV.append(SoilPercent[i])
      SensorCSV.append(tdsValue)
      SensorCSV.append(pH)

      AGlog(str(buf),SENSORS)
      DBlog(SensorCSV,DB_SENSORS)
      time.sleep(SENSOR_DELAY)
