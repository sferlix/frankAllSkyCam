import datetime
import time
import traceback
from datetime import datetime, timedelta
from frankAllSkyCam import suncalc2
from pytz import timezone
import pytz
import sys
import math
import os
from importlib import resources  # Python 3.7+
from configparser import ConfigParser
import socket

config = ConfigParser()
config.read(os.path.join(os.path.dirname(__file__), '', 'config.txt'))
latitude  = float(config['site']['latitude'])
longitude = float(config['site']['longitude'])
timeZone = str(config['site']['time_zone'])

def getTimes():

    try:
       valori=["",""]

       tz = timezone(timeZone)
       datacalcolo = datetime.now(tz)
       # print("Orario attuale = "+str(datacalcolo))

       # get sun information
       sc = suncalc2.getTimes(datacalcolo, latitude, longitude)
       s_set  = datetime.strptime(sc["sunset"],"%Y-%m-%d %H:%M:%S")
       dusk_ = datetime.strptime(sc["dusk"],"%Y-%m-%d %H:%M:%S")
       dawn_ = datetime.strptime(sc["dawn"],"%Y-%m-%d %H:%M:%S")
       s_rise = datetime.strptime(sc["sunrise"],"%Y-%m-%d %H:%M:%S")

       dawn = dawn_.astimezone(tz)
       srise  = s_rise.astimezone(tz)
       sset   = s_set.astimezone(tz)
       dusk = dusk_.astimezone(tz)
 
       #print("dawn           = "+str(dawn) + " > " +  str(dawn.hour) + ":" + str(dawn.minute))
       #print("dusk           = "+str(dusk) + " > " +  str(dusk.hour) + ":" + str(dusk.minute))
      
       if dawn.minute > 30:
          mat = dawn.hour + 1
       else:
          mat = dawn.hour

       if dusk.minute > 30:
          ser = dusk.hour + 1
       else:
          ser = dusk.hour

       try:
           with open('./AllSkyCrontab.txt', 'w') as f:
              f.write("*/1 " + str(mat) +"-" + str(ser-1)+ " * * * python3 -m frankAllSkyCam >/dev/null 2>&1\n")
              f.write("*/3 " + str(ser) +"-23 * * * python3 -m frankAllSkyCam >/dev/null 2>&1\n")
              f.write("*/3 0-" + str(mat-1)+" * * *  python3 -m frankAllSkyCam >/dev/null 2>&1\n")
              f.write("0 1 * * * python3 -m frankAllSkyCam.allskycamdelete >/dev/null 2>&1\n")   
              f.write("0 8 * * * python3 -m frankAllSkyCam.timelapse >/dev/null 2>&1\n")
              f.write("0 8 * * * python3 -m frankAllSkyCam.startrail >/dev/null 2>&1\n")
              f.write("*/15 * * * * python3 -m frankAllSkyCam.watchDog >/dev/null 2>&1\n")
              f.write("0 0 1 1 * python3 -m frankAllSkyCam.crontab >/dev/null 2>&1\n")
              f.close()
              os.system("crontab -r")
              os.system("crontab ./AllSkyCrontab.txt")
              os.system("rm ./AllSkyCrontab.txt")

       except Exception as e:
           print("error while creating crontab: " + str(e))
           print(traceback.format_exc())

    except Exception as e:
       print("type error: " + str(e))
       print(traceback.format_exc())
    return

def main():
    s = getTimes()
    return
	
if __name__ == "__main__":
   main()




