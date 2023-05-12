# AG config and support functions

import time
from datetime import datetime
import sys
import csv
import serial

################### Constants #################################################################
VERSION = 6                   # Version of this code
NUM_WATER_VALVES = 3          # Number of water valves
FLOW_PIN_INPUT = 25           # Pin that flow meter is attached
WATER_CYCLE_TIME = 30         # Time between running a water cycle in seconds
PUMP_DELAY = 1                # Time between stopping and starting pump to avoid back pressure
WATER_CYCLE_LENGTH = 5        # Time to water per valve per cycle in seconds
PRINT_TO_CONSOLE = True       # Print to console as well as log
SENSOR_DELAY = 3              # Time delay between sensor polls in seconds
SOIL_DRY = 49000              # Raw value when soil is totally dry
SOIL_WET = 21000              # Raw value when soil is totally wet
NUM_SOIL_SENSORS = 2          # Number of soil sensors attached to system
ROOM_TEMPERATURE = 25         # Temperature of room in celsius - used for TDS formula 
USB_PORT = "/dev/ttyUSB0"     # USB port pH meter is connected to
SYS = "AGsys.log"             # AG system log name
PUMP = "AGpump.log"           # AG pump log name
DB_PUMP = "AGpump.csv"        # AG pump log for csv
SENSORS = "AGsensors.log"     # AG sensor log name
DB_SENSORS = "AGsensors.csv"  # AG sensors log for csv
ERROR = "AGerror.log"         # Log for system errors
###############################################################################################

# Log messages to main log and print to screen if required
def AGsys(buf):
   s = datetime.now().strftime("%m%d%y %H:%M:%S") + "  " + buf
   if (PRINT_TO_CONSOLE):
      print(s)
      sys.stdout.flush()
   s = s + "\n"
   try:
      file = open(SYS,"a")
      file.write(s)
      file.close()
   except Exception:
      print("ERROR - Could not write to file: " + SYS)

# Log messages to general logs
def AGlog(buf,file_name):
   s = datetime.now().strftime("%m%d%y %H:%M:%S") + "  " + buf + "\n"
   try:
      file = open(file_name,"a")
      file.write(s)
      file.close()
   except Exception:
      print("ERROR - Could not write to file: " + file_name)

# Log message to CSV for DB inserts
def DBlog(buf,file_name):
   s = str(datetime.now())
   buf.insert(0,s) # Add timestamp to begining of the list to write
   try:
      file = open(file_name,"a")
      data_writer = csv.writer(file)
      data_writer.writerow(buf)
      file.close()
   except Exception:
      print("ERROR - Could not write to file: " + file_name)
