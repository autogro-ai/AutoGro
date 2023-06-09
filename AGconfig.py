# AG config and support functions
# V14

import time
from datetime import datetime
import sys
import csv
import serial
import json
import copy
import requests

################### Constants #################################################################
VERSION = 14                           # Version of this code
NUM_WATER_VALVES = 5                   # Number of water valves
MAX_WATER_VALVES = 5                   # Max number of system water valves, used for pump API call
FLOW_PIN_INPUT = 25                    # Pin that flow meter is attached
WATER_CYCLE_TIME = 180                 # Time between running a water cycle in seconds
PUMP_DELAY = 1                         # Time between stopping and starting pump to avoid back pressure
WATER_CYCLE_LENGTH = 10                # Time to water per valve per cycle in seconds
PRINT_TO_CONSOLE = True                # Print to console as well as log
BALANCE_PH = True                      # Is pH auto balance enabled?
IDEAL_PH = 6.5                         # pH value the system will attemp to maintain
PH_SPREAD = .5                         # Acceptable pH value spread before system takes action
WEB_API = True                         # Enable or disable write to web API
PH_ENABLED = True                      # Is pH sensor enabled?
PH_DOWN_RELAY = 7                      # Relay that controls pH down fluid
PH_UP_RELAY = 6                        # Relay that controls pH up fluid
PH_VALVE_TIME = 5                      # Time to open valve to adjust pH in seconds
PH_BALANCE_INTERVAL = 300             # The shortest time between pH auto adjustments (takes place after water cycle)
TDS_ENABLED = True                     # Is TDS water quality sensor enabled?
TDS_SAMPLES = 4                        # Number of TDS samples to average together for result
SENSOR_TIME_API = 180                 # Time delay between sensor API publications in seconds (1800 = 30 min)
SENSOR_TIME_CSV = 600                  # Time delay between sensor CSV publications in seconds (600 = 10 min)
SENSOR_TIME_DIAG = 5                   # Time delay between sensor DIAG publications in seconds
SOIL_DRY = 49000                       # Raw value when soil is totally dry
SOIL_WET = 21000                       # Raw value when soil is totally wet
NUM_SOIL_SENSORS = 5                   # Number of soil sensors attached to system
MAX_SOIL_SENSORS = 5                   # Max number of soil sensors system supports, used to fully populate DB
ROOM_TEMPERATURE = 25                  # Temperature of room in celsius - used for TDS formula
USB_PORT = "/dev/ttyUSB0"              # USB port pH meter is connected to
SYS = "AGsys.log"                      # AG system log name
PUMP = "AGpump.log"                    # AG pump log name
CSV_PUMP = "AGpump.csv"                # AG pump log for csv
SENSORS = "AGsensors.log"              # AG sensor log name
CSV_SENSORS = "AGsensors.csv"          # AG sensors log for csv
ERROR = "AGerror.log"                  # Log for system errors
SENSOR_JSON_FILE = "sensor_json.log"   # Log file that records the sensor json data passed to the web api
PUMP_JSON_FILE = "pump_json.log"       # Log file that records the pump json data passed to the web api
PUMP_URL = "XXXXXXXXXXXXXXXXXXXXXXXXX" # Location of pump API endpoint
SENSOR_URL = "XXXXXXXXXXXXXXXXXXXXXXX" # Location of sensor API endpoint
###############################################################################################

# Global variables used across files
global_pH = -1  # Global pH value 

######## Log messages to main log and print to screen if required
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

######## Log messages to general diagnostic logs
def AGlog(buf,file_name):
   s = datetime.now().strftime("%m%d%y %H:%M:%S") + "  " + buf + "\n"
   try:
      file = open(file_name,"a")
      file.write(s)
      file.close()
   except Exception:
      print("ERROR - Could not write to file: " + file_name)

####### Log message to CSV
def CSVlog(buf_list,file_name):
   s = str(datetime.now())
   # Making clone / copy of sent in list to preserve it for calling programs
   buf_list_copy = copy.deepcopy(buf_list)
   buf_list_copy.insert(0,s)
   try:
      file = open(file_name,"a")
      data_writer = csv.writer(file)
      data_writer.writerow(buf_list_copy)
      file.close()
   except Exception:
      print("ERROR - Could not write to file: " + file_name)

####### Call Sensor web API
def APIsensor(buf_list): # This list is max soil sensors, then tds, then pH
   url = SENSOR_URL
   data = {} # Next few lines create JSON for Sensor API call
   for i in range (0,MAX_SOIL_SENSORS):
      data["soil_" + str(i+1) + "_wet"] = buf_list[i] # Key soil_x_wet starts with x=1
   data["tds"] = buf_list[MAX_SOIL_SENSORS]
   data["ph"] = buf_list[MAX_SOIL_SENSORS + 1]
   data["accessed"] = str(datetime.now())

   # Web API call for sensors
   web_success = False
   if (WEB_API):
      AGsys("Sending data to sensor web API")
      try:
         response = requests.post(url, data=data, timeout=5)
         if (response.status_code != 200):
            AGlog("ERROR - API sensor web call failed.  Return code: " + str(response.status_code),ERROR)
         else:
            web_success = True
            AGsys("Sensor web API successful")
      except Exception as e:
         AGlog("ERROR - Exception on sensor web API call, possible timeout",ERROR)

   # Log json in clear text to log for diagnostics
   try:
      file = open (SENSOR_JSON_FILE,"a")
      file.write(json.dumps(data,indent=4))
      if (WEB_API):
         if (web_success):
            file.write("\nSuccessful call\n")
         else:
            file.write("\nERROR\n")
      else:
         file.write("\nWeb API not enabled\n")
      file.close()
   except Exception:
      print("ERROR - Could not write to file: " + SENSOR_JSON_FILE)


####### Call Pump web API
def APIpump(Relay_Status,flow): # String that identifies valve and then flow meter value
   url = PUMP_URL
   data = {} # Next several lines create JSON for Sensor API call

   if (Relay_Status[0] == True):  # Relay zero is always the pump
      data["pump_status"] = 100   # Picked zero and hundred for backend graphing purposes
   else:
      data["pump_status"] = 0

   data["flow_meter_rotations"] = flow

   for i in range (0,MAX_WATER_VALVES):
      s = "valve_" + str(i+1) # key common to all

      if (i >= NUM_WATER_VALVES):
         data[s] = ""
      elif (Relay_Status[i+1] == True):
         data[s] =  100 # Picked zero and hundred for backend graphinc purposes
      else:
         data[s] = 0

   data["accessed"] = str(datetime.now())

   # Web API call for pump
   web_success = False
   if (WEB_API):
      AGsys("Sending data to pump web API")
      try:
         response = requests.post(url, data=data, timeout=5)
         if (response.status_code != 200):
            AGlog("ERROR - API pump web call failed.  Return code: " + str(response.status_code),ERROR)
         else:
            web_success = True
            AGsys("Pump web API successful")
      except Exception as e:
         AGlog("ERROR - Exception on pump web API call, possible timeout",ERROR)

   # Log json in clear text to log for diagnostics
   try:
      file = open (PUMP_JSON_FILE,"a")
      file.write(json.dumps(data,indent=4))
      if (WEB_API):
         if (web_success):
            file.write("\nSuccessful call\n")
         else:
            file.write("\nERROR\n")
      else:
         file.write("\nWeb API not enabled\n")
      file.close()
   except Exception:
      print("ERROR - Could not write to file: " + PUMP_JSON_FILE)
