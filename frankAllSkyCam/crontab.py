'''
 this file will install the crontab jobs to make
 everything working
'''

import datetime
import time
import traceback
from datetime import datetime, timedelta
from frankAllSkyCam import fileManager
import sys
import math
import os
import subprocess
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

# tags every cron line this script writes, so readCrontab() replaces exactly its own lines
# on a rerun and leaves unrelated user entries alone
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

              # mat/ser split the day into 3 hour ranges: guard the edges so an extreme-latitude
              # dawn/dusk can't produce an invalid range like "0--1" (crontab rejects the whole file)
              if mat <= ser - 1:
                 f.write("*/1 " + str(mat) +"-" + str(ser-1)+ " * * * python3 -m frankAllSkyCam >" + logFolder + "/capture.log 2>&1 " + MARKER + "\n")
              # night hours run every 2 min: a night cycle (exposure up to esp_secs plus overhead)
              # often takes over 60s, so a 1-min interval would only queue runs behind the camera
              # lock. Daytime has near-instant exposure and keeps */1.
              f.write("*/2 " + str(ser) +"-23 * * * python3 -m frankAllSkyCam >" + logFolder + "/capture.log 2>&1 " + MARKER + "\n")
              if mat >= 1:
                 f.write("*/2 0-" + str(mat-1)+" * * *  python3 -m frankAllSkyCam >" + logFolder + "/capture.log 2>&1 " + MARKER + "\n")
              f.write("*/15 * * * * python3 -m frankAllSkyCam.watchDog >" + logFolder + "/watchdog.log 2>&1 " + MARKER + "\n")
              # generateExtraData.py lives in ~/frankAllSkyCam/tools/ (user-editable, not replaced by
              # upgrades), so it is invoked by absolute path rather than -m. It also switches the
              # dew heater.
              f.write("*/5 * * * * python3 " + appPath + "tools/generateExtraData.py >" + logFolder + "/generateExtraData.log 2>&1 " + MARKER + "\n")
              f.write("0 1 * * * python3 -m frankAllSkyCam.allskycamdelete >" + logFolder + "/allskycamdelete.log 2>&1 " + MARKER + "\n")
              f.write("50 7 * * * python3 -m frankAllSkyCam.startrail >" + logFolder + "/startrail.log 2>&1 " + MARKER + "\n")
              f.write("0 8 * * * python3 -m frankAllSkyCam.timelapse >" + logFolder + "/timelapse.log 2>&1 " + MARKER + "\n")
              f.write("0 */6 * * * python3 -m frankAllSkyCam.calculateEphem >" + logFolder + "/calculateEphem.log 2>&1 " + MARKER + "\n")
              f.write("0 0 1 1 * python3 -m frankAllSkyCam.crontab >" + logFolder + "/crontab.log 2>&1 " + MARKER + "\n")
              f.close()

              # install the new file directly: crontab replaces the whole crontab atomically and
              # rejects a malformed file, so a bad file leaves the previous crontab in place
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
    # migration: recognizes lines written before MARKER existed ("-m frankAllSkyCam" and this
    # install's own generateExtraData.py path)
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
            # keep this line: it isn't one of ours. Only MARKER lines (and legacy lines, see
            # _is_legacy_line) are replaced.
            crontabLines.append(line)


    file1.close()
    os.system("rm ./prev_crontab.txt")
    return crontabLines


# substrings of the cron lines that must be paused during exclusive camera access
# (e.g. capturedarks.py); other jobs (allskycamdelete, startrail, timelapse,
# calculateEphem, generateExtraData) keep running:
#   - the capture job ("python3 -m frankAllSkyCam >"; the trailing " >" keeps it from
#     matching "-m frankAllSkyCam.watchDog"), which would race for the camera
#   - the watchdog ("-m frankAllSkyCam.watchDog"), which reboots the Pi when no new
#     frame appeared within rebootAfter minutes: a long session would trigger it
PAUSABLE_JOB_SUBSTRINGS = ("python3 -m frankAllSkyCam >", "-m frankAllSkyCam.watchDog")


def _currentCrontabLines():
    '''Returns the current real crontab as a list of lines, or [] if none is installed yet.'''
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return result.stdout.splitlines(keepends=True)


def _installCrontabLines(lines):
    # same temp file + `crontab <file>` pattern as getTimes(): a malformed file is
    # rejected as a whole, so this fails safe
    tmp_path = appPath + "_tmp_crontab_install.txt"
    with open(tmp_path, "w") as f:
        f.writelines(lines)
    os.system("crontab " + tmp_path)
    os.remove(tmp_path)


def _pausedLines(lines):
    '''
    Pure transform: comments out (never deletes) the lines matching
    PAUSABLE_JOB_SUBSTRINGS and leaves every other line untouched. Separate from
    pauseCaptureJobs() so it can be unit tested without a crontab.
    '''
    return [
        "#" + line if (not line.startswith("#") and
                        any(s in line for s in PAUSABLE_JOB_SUBSTRINGS))
        else line
        for line in lines
    ]


def pauseCaptureJobs():
    '''
    Comments out (never deletes) the capture and watchdog cron lines (see
    PAUSABLE_JOB_SUBSTRINGS); other jobs keep running. Returns the original crontab
    lines, to pass to resumeCaptureJobs() in a finally block.
    '''
    original = _currentCrontabLines()
    _installCrontabLines(_pausedLines(original))
    return original


def resumeCaptureJobs(original_lines):
    '''Restores the exact crontab lines a prior pauseCaptureJobs() call returned.'''
    _installCrontabLines(original_lines)


def main():
    s = getTimes()
    return


if __name__ == "__main__":
   main()




