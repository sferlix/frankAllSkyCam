'''
 This file will clean old image folders aftwer #days_retention days
 you con configure #days_retention in config.txt
'''

import datetime
import os
import shutil
from zoneinfo import ZoneInfo
from configparser import ConfigParser
from frankAllSkyCam import fileManager


config = ConfigParser()
configFileName = fileManager.getConfigFileName()
config.read(configFileName)
appPath = os.path.expanduser("~") + "/frankAllSkyCam/"

time_zone = str(config['site']['time_zone'])
logFolder = appPath + str(config['system']['logFolder'])
outputFolder = appPath + str(config['system']['otuputFolder'])

days_retention = int(config['system']['days_retention'])

def main():
    tz = ZoneInfo(time_zone)
    z = datetime.datetime.now(tz)
    cutoff = (z+datetime.timedelta(days=-days_retention)).strftime("%Y%m%d")

    if not os.path.isdir(outputFolder):
       return

    for name in os.listdir(outputFolder):
        full = os.path.join(outputFolder, name)
        if not os.path.isdir(full):
           continue
        if not (len(name) == 8 and name.isdigit()):
           continue
        if name < cutoff:
           print("Deleting old folder: " + full)
           shutil.rmtree(full, ignore_errors=True)
    pass

if __name__ == "__main__":
    main()


