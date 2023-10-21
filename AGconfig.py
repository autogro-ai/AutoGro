# AG config and support functions
# V20

import time
from datetime import datetime
import sys
import csv
import serial
import json
import copy
import requests
from urllib.request import urlopen

################### Constants NON remote config  #################################################################
VERSION = 20                           # Version of this code
MAX_WATER_VALVES = 5                   # Max number of system water valves, used for pump API call
FLOW_PIN_INPUT = 25                    # Pin that flow meter is attached
PUMP_DELAY = 1                         # Time between stopping and starting pump to avoid back pressure
PRINT_TO_CONSOLE = True                # Print to console as well as log
PH_DOWN_RELAY = 7                      # Relay that controls pH down fluid
PH_UP_RELAY = 6                        # Relay that controls pH up fluid
SENSOR_TIME_DIAG = 5                   # Time delay between sensor DIAG publications in seconds
MAX_SOIL_SENSORS = 5                   # Max number of soil sensors system supports, used to fully populate DB
LOGGING_TIMER = 3                      # Time between general logging for water and pH cycles
SYS = "AGsys.log"                      # AG system log name
PUMP = "AGpump.log"                    # AG pump log name
SENSORS = "AGsensors.log"              # AG sensor log name
ERROR = "AGerror.log"                  # Log for system errors
SENSOR_JSON_FILE = "sensor_json.log"   # Log file that records the sensor json data passed to the web api
PUMP_JSON_FILE = "pump_json.log"       # Log file that records the pump json data passed to the web api
FILE_PARMS = "AG_Parms.txt"            # Parms config file, updated from remote API call
REMOTE_PARMS = False                   # Get remote parms from web api
REMOTE_PARM_INTERVAL = 30              # Time between getting remote parms in seconds
                                       # Remote config URL
REMOTE_CONFIG_URL = "https://autogro.pythonanywhere.com/autogro_app_api/XXXXXXXXX"
                                       # Location of USB reset command for pH USB bug
USB_RESET = "/home/pi/bin/AutoGro/usb_reset/fix_usb"
##################################################################################################################

############### Default runtime parms, override via file config or remote API #####################
run_parms = {
# Valve parms ##########
"valve1_active" : True,              # Valve 1 enabled - true / false
"valve1_time" : 600,                 # Valve 1 time between water cycles in seconds
"valve1_duration" : 10,              # Valve 1 duration that valve is running / watering
#
"valve2_active" : True,              # Valve 2 enabled - true / false
"valve2_time" : 600,                 # Valve 2 time between water cycles in seconds
"valve2_duration" : 10,              # Valve 2 duration that valve is running / watering
#
"valve3_active" : True,              # Valve 3 enabled - true / false
"valve3_time" : 600,                 # Valve 3 time between water cycles in seconds
"valve3_duration" : 10,              # Valve 3 duration that valve is running / watering
#
"valve4_active" : True,              # Valve 4 enabled - true / false
"valve4_time" : 600,                 # Valve 4 time between water cycles in seconds
"valve4_duration" : 10,              # Valve 4 duration that valve is running / watering
#
"valve5_active" : False,             # Valve 5 enabled - true / false
"valve5_time" : 600,                 # Valve 5 time between water cycles in seconds
"valve5_duration" : 10,              # Valve 5 duration that valve is running / watering
#
"water_refresh_cycle" : 900,         # Time in seconds between water refresh cycles, run pump with no valves open
"water_refresh_cycle_length" : 10,   # Time in seconds for water refresh cycle duration

# pH Routine parms ############
"ph_sensor_enabled" : True,          # Is pH sensor enabled?
"balance_ph" : True,                 # Should the system attempt to balance pH
"ideal_ph" : 6.5,                    # pH Target value for system, used in balance routine
"ph_spread" : .5,                    # +/- target range for pH centered on Ideal_pH value
"ph_valve_time" : 1,                 # Amount of time pH adjustement value will stay open
"ph_balance_interval" : 2000,        # Time between auto balance of pH in seconds
"ph_balance_water_limit" : 10,       # Closest the system will balance pH in proximity to water cycle, in seconds
"ph_balance_retry" : 30,             # If pH balance routine is in conflict with water cycle, this is next scheduled try in seconds
"ph_sensor_port" : "/dev/ttyUSB0",   # tty device that USB pH sensor is attached to

# Web APIs ###########
"enable_web_api" : True,             # Should sensor data be published to web api(s)?
                                     # PUMP_URL to send api data
"pump_url" : "https://autogro.pythonanywhere.com/XXXXXXX",
                                     # SENSIR_URL to send api data
"sensor_url" : "https://autogro.pythonanywhere.com/XXXXXXXX",

# Sensor parms #######
"enable_tds_meter" : True,           # Enabled TDS (water quality) sensor
"tds_samples" : 5,                   # Number of TDS readings to average together for result
"room_temperature" : 23,             # Room temperature for TDS calculation
"sensor_time_api" : 900,             # Time in seconds between reporting sensor data to web api
"soil_dry" : 49000,                  # Value from soil sensor for 100% dry
"soil_wet" : 21000,                  # Value from soil sesnsor for 100% wet
"number_of_soil_sensors" : 5         # Number of soil sensors active on system
}
###################################################################################################3

# Global variables used across files
global_pH = -1  # Global pH value

#Write json data to log
def write_json_to_log(data):
   for entry in data:
      AGsys("Key: " + str(entry).ljust(28) + " Value: " + str(data[entry]))

# Write the parm file to disk
def write_parm_file():
   try:
      with open(FILE_PARMS,"w") as convert_file:
         convert_file.write(json.dumps(run_parms, indent=2))
   except Exception:
      AGlog("Could not write parameter file to disk",ERROR)

# Read the parm file from disk, return empty dict for error
def read_parm_file():
   file_parms = {}
   try:
      file = open(FILE_PARMS,"r")
   except Exception:
      AGlog("Could not open parameter file on disk",ERROR)
      return file_parms # Could not open parm file
   try:
      file_parms = json.load(file)
   except Exception:
      AGlog("Could not parse parm file to json",ERROR)
   try:
      file.close()
   except Exception:
      AGlog("Could not close parm file on disk",ERROR)
      return file_parms
   return file_parms # All good, open, close and json parse

# Read parms from the remote api / webserver
def read_remote_parms():
   remote_parms = {}
   try:
      response = urlopen(REMOTE_CONFIG_URL,timeout=5)
      if (response.getcode() == 200):
         remote_parms = json.loads(response.read())
      if (remote_parms == {}):
         AGlog("Could not get api parm data from website",ERROR)
   except Exception as e:
      AGlog("Exception getting api parm data from website: " + str(e),ERROR)
   return remote_parms

# Check to see if data coming in is a valid bool
def check_bool_parm(new_parms, key): # Return true/false if running parm is changed
   if (key not in new_parms):
      AGsys("Key: " + key + " Not found in dictionary")
      return False
   if (type(new_parms[key]) != bool):
      AGsys("Key: " + key + " is not a bool")
      return False 
   if (new_parms[key] != True and new_parms[key] != False):
      AGsys("Key: " + key + " Invalid value")
      return False
   if (new_parms[key] != run_parms[key]):
      run_parms[key] = new_parms[key]
      AGsys("Key: " + key + " Updating value <<<<<<<<<<")
      return True
   else:
      AGsys("Key " + key + " is the same")
      return False

# Check to see if data coming in is a valid string
def check_string_parm(new_parms, key, length, sub_string): # Return true/false if running parm is changed
   if (key not in new_parms):
      AGsys("Key: " + key + " Not found in dictionary")
      return False
   if (type(new_parms[key]) != str):
      AGsys("Key: " + key + " is not a string")
      return False
   if (len(new_parms[key]) < length):
      AGsys("Key: " + key + " is too short")
      return False
   if (sub_string not in new_parms[key]):
      AGsys("Key: " + key + " is not valid")
      return False
   if (new_parms[key] != run_parms[key]):
      run_parms[key] = new_parms[key]
      AGsys("Key: " + key + " Updating value <<<<<<<<<<")
      return True
   else:
      AGsys("Key " + key + " is the same")
      return False

# Check to see if data coming in is a valid int or float and min/max range
def check_number_parm(new_parms,key,var_type,min_val,max_val): # Return true/false if running parm is changed
   if (key not in new_parms):
      AGsys("Key: " + key + " Not found in dictionary")
      return False
   if (var_type == int): # float can can cover int and float so checking both in this block
      if (type(new_parms[key]) != int):
         AGsys("Key: " + key + " is not integer variable type")
         return False
   else: # float check
      if (type(new_parms[key]) != int and type(new_parms[key]) != float):
         AGsys("Key: " + key + " is not integer or float type")
         return False
   if (new_parms[key] < min_val or new_parms[key] > max_val):
      AGsys("Key: " + key + " is out of range")
      return False
   if (new_parms[key] != run_parms[key]):
      run_parms[key] = new_parms[key]
      AGsys("Key: " + key + " Updating value <<<<<<<<<<<<<<")
      return True
   else:
      AGsys("Key " + key + " is the same")
      return False

# Check a new set of parms to update running parms
# These came from a file read or a API get request
# For ints or floats a range is checked for validity
# For stirngs, a length is checked as well as contents
def update_parms(new_parms):
   changed = False
   if (check_bool_parm(new_parms,"valve1_active")):
      changed = True
   if (check_bool_parm(new_parms,"valve2_active")):
      changed = True
   if (check_bool_parm(new_parms,"valve3_active")):
      changed = True
   if (check_bool_parm(new_parms,"valve4_active")):
      changed = True
   if (check_bool_parm(new_parms,"valve5_active")):
      changed = True
   if (check_number_parm(new_parms,"valve1_time",float,.1,500000)):
      changed = True
   if (check_number_parm(new_parms,"valve2_time",float,.1,500000)):
      changed = True
   if (check_number_parm(new_parms,"valve3_time",float,.1,500000)):
      changed = True
   if (check_number_parm(new_parms,"valve4_time",float,.1,500000)):
      changed = True
   if (check_number_parm(new_parms,"valve5_time",float,.1,500000)):
      changed = True
   if (check_number_parm(new_parms,"valve1_duration",float,.1,3600)):
      changed = True
   if (check_number_parm(new_parms,"valve2_duration",float,.1,3600)):
      changed = True
   if (check_number_parm(new_parms,"valve3_duration",float,.1,3600)):
      changed = True
   if (check_number_parm(new_parms,"valve4_duration",float,.1,3600)):
      changed = True
   if (check_number_parm(new_parms,"valve5_duration",float,.1,3600)):
      changed = True
   if (check_number_parm(new_parms,"water_refresh_cycle",float,.1,300000)):
      changed = True
   if (check_number_parm(new_parms,"water_refresh_cycle_length",float,.1,300000)):
      changed = True
   if (check_bool_parm(new_parms,"ph_sensor_enabled")):
      changed = True
   if (check_bool_parm(new_parms,"enable_web_api")):
      changed = True
   if (check_bool_parm(new_parms,"enable_tds_meter")):
      changed = True
   if (check_bool_parm(new_parms,"balance_ph")):
      changed = True
   if (check_number_parm(new_parms,"tds_samples",int,1,20)):
      changed = True
   if (check_number_parm(new_parms,"number_of_soil_sensors",int,1,5)):
      changed = True
   if (check_number_parm(new_parms,"soil_dry",int,1000,70000)):
      changed = True
   if (check_number_parm(new_parms,"soil_wet",int,1000,70000)):
      changed = True
   if (check_number_parm(new_parms,"ideal_ph",float,5,8)):
      changed = True
   if (check_number_parm(new_parms,"ph_spread",float,.1,2)):
      changed = True
   if (check_number_parm(new_parms,"ph_valve_time",float,.1,30)):
      changed = True
   if (check_number_parm(new_parms,"ph_balance_interval",float,20,300000)):
      changed = True
   if (check_number_parm(new_parms,"ph_balance_water_limit",float,30,300000)):
      changed = True
   if (check_number_parm(new_parms,"ph_balance_retry",float,5,300000)):
      changed = True
   if (check_number_parm(new_parms,"room_temperature",float,-23,49)):
      changed = True
   if (check_number_parm(new_parms,"sensor_time_api",float,.1,300000)):
      changed = True
   if (check_string_parm(new_parms,"ph_sensor_port",8,"/dev/tty")):
      changed = True
   if (check_string_parm(new_parms,"pump_url",10,"https://")):
      changed = True
   if (check_string_parm(new_parms,"sensor_url",10,"https://")):
      changed = True
   return changed

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

####### Call Sensor web API
def APIsensor(buf_list): # This list is max soil sensors, then tds, then pH
   url = run_parms["sensor_url"]
   data = {} # Next few lines create JSON for Sensor API call
   for i in range (0,MAX_SOIL_SENSORS):
      data["soil_" + str(i+1) + "_wet"] = buf_list[i] # Key soil_x_wet starts with x=1
   data["tds"] = buf_list[MAX_SOIL_SENSORS]
   data["ph"] = buf_list[MAX_SOIL_SENSORS + 1]
   data["accessed"] = str(datetime.now())

   # Web API call for sensors
   web_success = False
   if (run_parms["enable_web_api"]):
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
      if (run_parms["enable_web_api"]):
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
   url = run_parms["pump_url"]
   data = {} # Next several lines create JSON for Sensor API call

   if (Relay_Status[0] == True):  # Relay zero is always the pump
      data["pump_status"] = 100   # Picked zero and hundred for backend graphing purposes
   else:
      data["pump_status"] = 0

   data["flow_meter_rotations"] = flow

   for i in range (0,MAX_WATER_VALVES):
      s = "valve_" + str(i+1) # key common to all

      if (Relay_Status[i+1] == True):
         data[s] =  100 # Picked zero and hundred for backend graphinc purposes
      else:
         data[s] = 0

   data["accessed"] = str(datetime.now())

   # Web API call for pump
   web_success = False
   if (run_parms["enable_web_api"]):
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
      if (run_parms["enable_web_api"]):
         if (web_success):
            file.write("\nSuccessful call\n")
         else:
            file.write("\nERROR\n")
      else:
         file.write("\nWeb API not enabled\n")
      file.close()
   except Exception:
      print("ERROR - Could not write to file: " + PUMP_JSON_FILE)
