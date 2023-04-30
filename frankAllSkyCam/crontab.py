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
config.read(os.path.expanduser("~")+"/frankAllSkyCam/config.txt")
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
 
       if dawn.minute > 30:
          mat = dawn.hour + 1
       else:
          mat = dawn.hour

       if dusk.minute > 30:
          ser = dusk.hour + 1
       else:
          ser = dusk.hour

       linesToAdd = readCrontab()

       try:
           with open('./AllSkyCrontab.txt', 'w') as f:
              for element in linesToAdd:
                  f.write(element)
 
              f.write("*/1 " + str(mat) +"-" + str(ser-1)+ " * * * python3 -m frankAllSkyCam >/dev/null 2>&1\n")
              f.write("*/3 " + str(ser) +"-23 * * * python3 -m frankAllSkyCam >/dev/null 2>&1\n")
              f.write("*/3 0-" + str(mat-1)+" * * *  python3 -m frankAllSkyCam >/dev/null 2>&1\n")
              f.write("0 1 * * * python3 -m frankAllSkyCam.allskycamdelete >/dev/null 2>&1\n")
              f.write("0 8 * * * python3 -m frankAllSkyCam.timelapse >/dev/null 2>&1\n")
              f.write("50 7 * * * python3 -m frankAllSkyCam.startrail >/dev/null 2>&1\n")
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

def readCrontab():
    os.system("crontab -l > " + "./prev_crontab.txt")
    file1 = open('./prev_crontab.txt', 'r')
    count = 0
    crontabLines = ['#Crontab generated by frankAllSkyCam\n']
    while True:
        count += 1

        # Get next line from file
        line = file1.readline()
        # end of file is reached
        if not line:
            break

        if "frankAllSkyCam" not in line:
            # save this line
            crontabLines.append(line)


    file1.close()
    os.system("rm ./prev_crontab.txt")
    return crontabLines


def main():
    s = getTimes()
    return
	
if __name__ == "__main__":
   main()




