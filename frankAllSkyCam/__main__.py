'''
  main program frankAllSkycam
  by Francesco Sferlazza, 2023
'''

import os
import sys
import datetime
from fractions import Fraction
import time
from pytz import timezone
from importlib import resources  # Python 3.7+
from configparser import ConfigParser
from frankAllSkyCam import imageHeader, fileManager, drawtext, getextdata

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
rotation = int(config['resolution']['picture_rotation'])
picture_rotation = str(config['resolution']['picture_rotation'])

additional_params = str(config['libcamera']['additional_params'])

font_size   = int(config['font']['font_size'])
font_colorR = int(config['font']['font_colorR'])
font_colorG = int(config['font']['font_colorG'])
font_colorB = int(config['font']['font_colorB'])
font_color = [font_colorR,font_colorG,font_colorB]

et_use         = str(config['extra_text']['et_use'])
et_x_pos       = int(config['extra_text']['et_x_pos'])
et_y_pos       = int(config['extra_text']['et_y_pos'])
et_font_size   = int(config['extra_text']['et_font_size'])
et_font_colorR = int(config['extra_text']['et_font_colorR'])
et_font_colorG = int(config['extra_text']['et_font_colorG'])
et_font_colorB = int(config['extra_text']['et_font_colorB'])
et_font_color = [et_font_colorR,et_font_colorG,et_font_colorB]


sqm_le = config['sqm']['use_sqm_le']

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

    #parameters from imageHeader
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
    exposure  = s[13]
    sqm       = s[14]

    jpg_file_name = fileManager.getOutputFileName(outputFolder, x) + TL + ".jpg"
    print("executing capture:")

    command = "libcamera-still -n -o " + jpg_file_name
    command += " --width " + str(horiz)
    command += " --height "+ str(vert)
    command += " --immediate "
    if exposure >0:
       command +=" --shutter " + str(int(exposure)) + " "
       command += additional_params
    else:
       command += " --metering average "

    try:
       # ensure no libcamera is operating
       killcmd = "ps -ef|grep libcamera | grep -v color|awk '{print $2}'|xargs kill -9 1> /dev/null 2>&1"
       os.system(killcmd)
       print(killcmd)

       #launch the command line
       print(command)
       os.system(command)

       print("Image captured")

       extra_text = [""]
       if et_use =="y":
          #extra_text needed
          extra_string = getextdata.getData()
          extra_text = [extra_string, et_font_size, et_font_color, et_x_pos, et_y_pos]

       # print watermark
       drawtext.printWatermark(s, jpg_file_name, font_size, font_color, sqm_le, rotation, extra_text)

       #generate /update alive.txt to say we are still alive
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

    time.sleep(1)

    # transfer files to your local web server folder
    if outputLocalWebFile != "":
       fileManager.saveToWEB(jpg_file_name, outputLocalWebFile)

    # transfer files to your FTP server
    fileManager.saveToFTP(isFTP, jpg_file_name,FTP_server,FTP_login,FTP_pass,FTP_fileName+".jpg")

    print("AllSkyCam is done.")
    return


if __name__ == "__main__":
    main()

def outputDailyFolder():
   return outF



