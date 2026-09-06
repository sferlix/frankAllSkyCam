'''
 this file will install the crontab jobs to make
 everything working
'''

import datetime
import time
import traceback
from datetime import datetime, timedelta
from frankAllSkyCam import fileManager
from pytz import timezone
import pytz
import sys
import math
import os
from importlib import resources  # Python 3.7+
from configparser import ConfigParser
import socket
import ephem

config = ConfigParser()
configFileName = fileManager.getConfigFileName()
config.read(configFileName)

latitude  = config['site']['latitude']
longitude = config['site']['longitude']
timeZone = str(config['site']['time_zone'])

appPath = os.path.expanduser("~") + "/frankAllSkyCam/"
logFolder = appPath + str(config['system']['logFolder'])

# tags every cron line this script writes, so readCrontab() can recognize
# and replace exactly (only) its own lines on a rerun - a bare substring
# check on "frankAllSkyCam" also matched unrelated user cron entries that
# merely mentioned the name (e.g. a personal script path), silently
# deleting them. A trailing "#comment" is safe here: cron runs each line's
# command through a shell, and both sh and bash treat a bare "#" as
# starting a comment there, same as in any shell script.
MARKER = "#frankAllSkyCam-managed"

def getTimes():

    try:
       valori=["",""]

       # get sun information>>> 
       d = datetime.utcnow()

       mySite=ephem.Observer()
       mySite.lat=latitude
       mySite.lon=longitude
       mySite.date = ephem.Date(d)
       mySite.horizon ='-12'
       sun = ephem.Sun(mySite)

       dawn = ephem.localtime(mySite.next_rising(sun))
       dusk  = ephem.localtime(mySite.next_setting(sun))

 
       ''' 
       sc = suncalc2.getTimes(datacalcolo, latitude, longitude)
       s_set  = datetime.strptime(sc["sunset"],"%Y-%m-%d %H:%M:%S")
       dusk_ = datetime.strptime(sc["dusk"],"%Y-%m-%d %H:%M:%S")
       dawn_ = datetime.strptime(sc["dawn"],"%Y-%m-%d %H:%M:%S")
       s_rise = datetime.strptime(sc["sunrise"],"%Y-%m-%d %H:%M:%S")

       dawn = dawn_.astimezone(tz)
       srise  = s_rise.astimezone(tz)
       sset   = s_set.astimezone(tz)
       dusk = dusk_.astimezone(tz)
       '''

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

              # mat/ser split the day into 3 hour ranges below - guard the
              # edges (mat==0, or mat>ser-1) so an extreme-latitude dawn/dusk
              # time can't render an invalid range like "0--1" (crontab
              # rejects the whole file on invalid syntax, see below)
              if mat <= ser - 1:
                 f.write("*/1 " + str(mat) +"-" + str(ser-1)+ " * * * python3 -m frankAllSkyCam >" + logFolder + "/capture.log 2>&1 " + MARKER + "\n")
              f.write("*/1 " + str(ser) +"-23 * * * python3 -m frankAllSkyCam >" + logFolder + "/capture.log 2>&1 " + MARKER + "\n")
              if mat >= 1:
                 f.write("*/1 0-" + str(mat-1)+" * * *  python3 -m frankAllSkyCam >" + logFolder + "/capture.log 2>&1 " + MARKER + "\n")
              f.write("*/15 * * * * python3 -m frankAllSkyCam.watchDog >" + logFolder + "/watchdog.log 2>&1 " + MARKER + "\n")
              # generateExtraData.py lives outside the package (in ~/frankAllSkyCam/tools/,
              # user-editable, never overwritten by a package upgrade) so it's invoked by
              # absolute path rather than -m
              # also handles dew heater switching (merged from the former checkdew.py,
              # to avoid polling the same temp/dewpoint sensors from two separate jobs)
              f.write("*/5 * * * * python3 " + appPath + "tools/generateExtraData.py >" + logFolder + "/generateExtraData.log 2>&1 " + MARKER + "\n")
              f.write("0 1 * * * python3 -m frankAllSkyCam.allskycamdelete >" + logFolder + "/allskycamdelete.log 2>&1 " + MARKER + "\n")
              f.write("50 7 * * * python3 -m frankAllSkyCam.startrail >" + logFolder + "/startrail.log 2>&1 " + MARKER + "\n")
              f.write("0 8 * * * python3 -m frankAllSkyCam.timelapse >" + logFolder + "/timelapse.log 2>&1 " + MARKER + "\n")
              f.write("0 */6 * * * python3 -m frankAllSkyCam.calculateEphem >" + logFolder + "/calculateEphem.log 2>&1 " + MARKER + "\n")
              f.write("0 0 1 1 * python3 -m frankAllSkyCam.crontab >" + logFolder + "/crontab.log 2>&1 " + MARKER + "\n")
              f.close()

              # crontab <file> already atomically replaces the whole crontab
              # in one step - it was preceded by "crontab -r" (clear first),
              # which left a window where a syntax error in the new file
              # (crontab refuses the whole file, doesn't apply partially)
              # would leave the box with zero cron jobs instead of the old
              # ones. Just installing the new file directly means a bad file
              # fails safe, leaving the previous crontab in place.
              os.system("crontab ./AllSkyCrontab.txt")
              os.system("rm ./AllSkyCrontab.txt")

       except Exception as e:
           print("error while creating crontab: " + str(e))
           print(traceback.format_exc())

    except Exception as e:
       print("type error: " + str(e))
       print(traceback.format_exc())
    return

def _is_legacy_line(line):
    # one-time migration only: lines from before MARKER existed, still
    # narrower than the old bare "frankAllSkyCam" check - "-m frankAllSkyCam"
    # (module invocation) and this install's own generateExtraData.py path
    # are specific enough that an unrelated user cron entry is very unlikely
    # to collide, unlike the plain project name appearing anywhere.
    return ("-m frankAllSkyCam" in line
            or (appPath + "tools/generateExtraData.py") in line
            or line.startswith("#Crontab generated by frankAllSkyCam"))

def readCrontab():
    os.system("crontab -l > " + "./prev_crontab.txt")
    file1 = open('./prev_crontab.txt', 'r')
    count = 0
    crontabLines = ['#Crontab generated by frankAllSkyCam ' + MARKER + '\n']
    while True:
        count += 1

        # Get next line from file
        line = file1.readline()
        # end of file is reached
        if not line:
            break

        if MARKER not in line and not _is_legacy_line(line):
            # keep this line - it isn't one of ours. Was a bare
            # "frankAllSkyCam" substring check, which also matched (and
            # silently deleted) any unrelated user cron entry that happened
            # to mention the project name anywhere (e.g. a personal script
            # under ~/frankAllSkyCam/tools/). MARKER is written on every
            # line this script generates (see getTimes() above), so this
            # now only ever matches our own lines - _is_legacy_line() is
            # just a one-time bridge so pre-MARKER installs don't end up
            # with every job duplicated on their first regeneration.
            crontabLines.append(line)


    file1.close()
    os.system("rm ./prev_crontab.txt")
    return crontabLines


def main():
    s = getTimes()
    return


if __name__ == "__main__":
   main()




