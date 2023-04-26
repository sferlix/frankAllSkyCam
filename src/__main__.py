import os
import sys
import datetime
from fractions import Fraction
import time
from pytz import timezone
from importlib import resources  # Python 3.7+
from configparser import ConfigParser
from allskycam import imageHeader, fileManager, drawtext

config = ConfigParser()
config.read(os.path.join(os.path.dirname(__file__), '', 'config.txt'))
time_zone = str(config['site']['time_zone'])
inte = str(config['site']['inte'])

outputFolder = str(config['system']['otuputFolder'])
outputLocalWebFile = str(config['system']['outputLocalWebFile'])
horiz = str(config['resolution']['horiz'])
vert = str(config['resolution']['vert'])
picture_rotation = str(config['resolution']['picture_rotation'])

font_size = str(config['font']['font_size'])

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
    comando += " -n --width " + str(horiz) + " --height "+ str(vert)

    if esposiz >0:
       #comando +=" -ag 16 -bm -st -ex off -drc high -t 1  -ss " + str(esposiz)
       comando +=" --gain 18 --awbgains 2.2,2.2 --shutter " + str(int(esposiz)) 
    else:
       comando += " --metering average "
       #comando +=" -ex auto -awb auto "  #-br 45 -co 5"
       #comando +="   --denoise cdn_hq "
    comando += " --immediate " 
    try:
       # ensure no libcamera is operating
       killcmd = "ps -ef|grep libcamera-still| grep -v color|awk '{print $2}'|xargs kill -9 1> /dev/null 2>&1"
       os.system(killcmd)

       print(comando)
       os.system(comando)

       # print watermark
       drawtext.printWatermark(s, nomefile)

       #textcommand = "convert " + nomefile +" -gravity North -fill white -pointsize 19 -annotate +0+0 ' " + header + "' " + nomefile
       #print(textcommand)
       #os.system(textcommand)

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



