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
from frankAllSkyCam import fileManager, drawtext, getextdata, logos, calculateEphem, sqmreader, exposurecalc

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

additional_night_params = str(config['libcamera']['additional_night_params'])
additional_day_params = str(config['libcamera']['additional_day_params'])

font_size   = int(config['font']['font_size'])
font_colorR = int(config['font']['font_colorR'])
font_colorG = int(config['font']['font_colorG'])
font_colorB = int(config['font']['font_colorB'])
font_color = [font_colorR,font_colorG,font_colorB]

top_left_x     = int(config['text_coords']['top_left_x'])
top_left_y     = int(config['text_coords']['top_left_y'])
top_right_x    = int(config['text_coords']['top_right_x'])
top_right_y    = int(config['text_coords']['top_right_y'])
bottom_left_x  = int(config['text_coords']['bottom_left_x'])
bottom_left_y  = int(config['text_coords']['bottom_left_y'])
bottom_right_x = int(config['text_coords']['bottom_right_x'])
bottom_right_y = int(config['text_coords']['bottom_right_y'])
top_center_x   = int(config['text_coords']['top_center_x'])
top_center_y   = int(config['text_coords']['top_center_y'])

text_positions = [[top_left_x,top_left_y],[top_right_x,top_right_y],[bottom_left_x,bottom_left_y],[bottom_right_x,bottom_right_y],[top_center_x,top_center_y]]

et_use         = str(config['extra_text']['et_use'])
et_data_file   = str(config['extra_text']['et_data_file'])
et_x_pos       = int(config['extra_text']['et_x_pos'])
et_y_pos       = int(config['extra_text']['et_y_pos'])
et_font_size   = int(config['extra_text']['et_font_size'])
et_font_colorR = int(config['extra_text']['et_font_colorR'])
et_font_colorG = int(config['extra_text']['et_font_colorG'])
et_font_colorB = int(config['extra_text']['et_font_colorB'])
et_font_color = [et_font_colorR,et_font_colorG,et_font_colorB]

compass_filename = str(config['compass']['compass_filename'])
compass_x_pos = int(config['compass']['compass_x_pos'])
compass_y_pos = int(config['compass']['compass_y_pos'])
compass_rot_angle = int(config['compass']['compass_rot_angle'])

logo_filename = str(config['logo']['logo_filename'])
logo_x_pos = int(config['logo']['logo_x_pos'])
logo_y_pos = int(config['logo']['logo_y_pos'])

phase_filename = str(config['moon_phase_img']['moon_filename'])
phase_x_pos = int(config['moon_phase_img']['moon_x_pos'])
phase_y_pos = int(config['moon_phase_img']['moon_y_pos'])

jupiter_x_pos = int(config['planets']['jupiter_x_pos'])
jupiter_y_pos = int(config['planets']['jupiter_y_pos'])
mars_x_pos = int(config['planets']['mars_x_pos'])
mars_y_pos = int(config['planets']['mars_y_pos'])
saturn_x_pos = int(config['planets']['saturn_x_pos'])
saturn_y_pos = int(config['planets']['saturn_y_pos'])
venus_x_pos = int(config['planets']['venus_x_pos'])
venus_y_pos = int(config['planets']['venus_y_pos'])

esp_secs = float(config['exposure']['esp_secs'])
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

    data = calculateEphem.calculate(x)
    sqm = readsqm()
    exposure = calculateExposure(sqm)

    data["sqm"] = sqm
    data["exposure"] = exposure
    data["inte"] = inte

    calculateEphem.printData(data)
    #max exposure (esp_secs from config.txt) wins over the calculated exposure
    if exposure > esp_secs:
       exposure = esp_secs


    jpg_file_name = fileManager.getOutputFileName(outputFolder, x) + data["suffisso"] + ".jpg"
    print("executing capture:")

    command = "libcamera-still -n -o " + jpg_file_name
    command += " --width " + str(horiz)
    command += " --height "+ str(vert)
    command += " --immediate "
    if exposure >0:
       exposure = exposure * 1000000
       command +=" --shutter " + str(int(exposure)) + " "
       command += additional_night_params
    else:
       command += additional_day_params

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
          extra_string = getextdata.getData(et_data_file)
          extra_text = [extra_string, et_font_size, et_font_color, et_x_pos, et_y_pos]

       # print data dictionary on the allsky image
       drawtext.printWatermark(data, jpg_file_name, font_size, font_color, sqm_le, rotation, text_positions, extra_text)

       '''
       # add compass png on the allsky image
       if compass_filename != "":
          print(compass_filename)
          logos.imagePaste(jpg_file_name, compass_filename, compass_x_pos, compass_y_pos, compass_rot_angle)

       # add logo png on the allsky image
       if logo_filename != "":
          print(logo_filename)
          logos.imagePaste(jpg_file_name, logo_filename, logo_x_pos, logo_y_pos, 0)

       # add moon phase image on the allsky image
       if phase_filename != "":
          print(phase_filename)
          logos.imagePaste(jpg_file_name, phase_filename, phase_x_pos, phase_y_pos, 0)

       print("before_logo")
       '''
       images = {
           "logo": [logo_filename != "", logo_filename, logo_x_pos, logo_y_pos, 0],
           "phase":  [phase_filename != "", phase_filename, phase_x_pos, phase_y_pos, 0],
           "compass": [compass_filename != "", compass_filename, compass_x_pos, compass_y_pos, compass_rot_angle],
           "jupiter": [data["Jupiter"], "jupiter.png", jupiter_x_pos, jupiter_y_pos, 0],
           "mars": [data["Mars"], "mars.png", mars_x_pos, mars_y_pos, 0],
           "saturn": [data["Saturn"], "saturn.png", saturn_x_pos, saturn_y_pos, 0],
           "venus": [data["Venus"], "venus.png", venus_x_pos, venus_y_pos, 0]
       }

       print(images)
       logos.imagesPaste(images, jpg_file_name)

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

def readsqm():
   sq=0
   try:
      sq = sqmreader.readSQM()
   except:
      print("Error while calculating SQM")
   print("sqm = " + str(sq))
   return sq

def calculateExposure(sq):
   if sq < 9:
      # no need to change the exposure.
      return 0
   ex = exposurecalc.getExposure(sq)
   return ex


if __name__ == "__main__":
    main()

def outputDailyFolder():
   return outF

