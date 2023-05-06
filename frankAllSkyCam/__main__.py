import os
import sys
import datetime
from fractions import Fraction
import time
from pytz import timezone
from importlib import resources  # Python 3.7+
from configparser import ConfigParser
from frankAllSkyCam import imageHeader, fileManager, drawtext

config = ConfigParser()
configFileName = fileManager.getConfigFileName()
config.read(configFileName)
appPath = os.path.expanduser("~") + "/frankAllSkyCam/"

time_zone = str(config['site']['time_zone'])
inte = str(config['site']['inte'])

logFolder = appPath + str(config['system']['logFolder'])
outputFolder = appPath + str(config['system']['otuputFolder'])
outputLocalWebFile = str(config['system']['outputLocalWebFile'])
horiz = str(config['resolution']['horiz'])
vert = str(config['resolution']['vert'])
picture_rotation = str(config['resolution']['picture_rotation'])

additional_params = str(config['libcamera']['additional_params'])

font_size = int(config['font']['font_size'])
font_colorR = int(config['font']['font_colorR'])
font_colorG = int(config['font']['font_colorG'])
font_colorB = int(config['font']['font_colorB'])
font_color = [font_colorR,font_colorG,font_colorB]

isFTP = str(config['ftp']['isFTP'])=='True'
FTP_server = str(config['ftp']['FTP_server'])
FTP_login = str(config['ftp']['FTP_login'])
FTP_pass = str(config['ftp']['FTP_pass'])
FTP_uploadFolder = str(config['ftp']['FTP_uploadFolder'])
FTP_fileNameAllSkyImg = str(config['ftp']['FTP_fileNameAllSkyImgJPG'])
FTP_fileName = FTP_uploadFolder + "/" + FTP_fileNameAllSkyImg
tz = timezone(time_zone)
x = datetime.datetime.now(tz)

def main():

    print("Execution started at: " +str(x))
    s = imageHeader.getHeader(x)

    data      = s[0]
    ora       = s[1]
    s[2] = inte
    TL        = s[4]
    moon_rise = s[5]
    moon_set  = s[6]
    srise     = s[7]
    sset      = s[8]
    NS        = s[9]
    NE        = s[10]
    phase     = s[11]
    fract     = s[12]
    esposiz   = s[13]
    sqm       = s[14]

    nomefile = fileManager.getOutputFileName(outputFolder, x) + TL + ".jpg"
    print("executing capture:")

    comando = "libcamera-still -o " + nomefile
    comando += " -n --width " + str(horiz) + " --height "+ str(vert) + " --immediate "

    if esposiz >0:
       comando +=" --shutter " + str(int(esposiz)) + " "
       comando += additional_params
    else:
       comando += " --metering average "

    try:
       # ensure no libcamera is operating
       killcmd = "ps -ef|grep libcamera-still| grep -v color|awk '{print $2}'|xargs kill -9 1> /dev/null 2>&1"
       os.system(killcmd)

       print(comando)
       os.system(comando)

       print("Image captured")
       # print watermark
       drawtext.printWatermark(s, nomefile, font_size, font_color)

       textcommand = "touch " + logFolder +  "/alive.txt"
       os.system(textcommand)

       pass
    except:
       print("ERROR: " + str(sys.exc_info()[0]))
       pass
       return
    finally:
       z=datetime.datetime.now(tz)
       print("Execution time: " + str(abs(z-x).seconds) +" secs")

    time.sleep(2)
    fileManager.saveToWEB(nomefile, outputLocalWebFile)
    fileManager.saveToFTP(isFTP, nomefile,FTP_server,FTP_login,FTP_pass,FTP_fileName+".jpg")

    print("AllSkyCam is done.")
    return


if __name__ == "__main__":
    main()

def outputDailyFolder():
   return outF



