import datetime
import os
from pytz import timezone
from configparser import ConfigParser

config = ConfigParser()
configFileName = fileManager.getConfigFileName()
config.read(configFileName)
appPath = os.path.expanduser("~") + "/frankAllSkyCam/"

time_zone = str(config['site']['time_zone'])
logFolder = appPath + str(config['system']['logFolder'])
outputFolder = appPath + str(config['system']['otuputFolder'])

days_retention = int(config['system']['days_retention'])

def main():
    tz = timezone(time_zone)
    x = datetime.datetime.now(tz)
    z=datetime.datetime.now(tz)
    outputDir = outputFolder + "/" + (z+datetime.timedelta(days=-days_retention)).strftime("%Y%m%d")
    comando ="rm " + outputDir +"/*.*;rmdir " + outputDir
    print(comando)
    os.system(comando)
    pass

if __name__ == "__main__":
    main()


