import datetime
import os
from pytz import timezone
from configparser import ConfigParser

config = ConfigParser()
config.read(os.path.join(os.path.dirname(__file__), '', 'config.txt'))

time_zone = str(config['site']['time_zone'])
outputFolder = str(config['system']['otuputFolder'])
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


