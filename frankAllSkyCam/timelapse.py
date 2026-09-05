'''

this file generates timelapses basing on ffmpeg
parameters may be set in config.txt, section [timelapse]

'''
import ftplib
import datetime
import time
import os
from pytz import timezone
from os import path
from configparser import ConfigParser
from frankAllSkyCam import fileManager

config = ConfigParser()
configFileName = fileManager.getConfigFileName()
config.read(configFileName)
appPath = os.path.expanduser("~") + "/frankAllSkyCam/"

logFolder = appPath + str(config['system']['logFolder'])
outputFolder = appPath + str(config['system']['otuputFolder'])

time_zone = str(config['site']['time_zone'])

tl_horiz = str(config['timelapse']['tl_horiz'])
tl_vert = str(config['timelapse']['tl_vert'])
framerate = str(config['timelapse']['framerate'])
nightTL = str(config['timelapse']['nightTL'])=='True'
fullTL = str(config['timelapse']['fullTL'])=='True'
# optional - fallback() keeps this working on existing config.txt files that
# predate this feature (no re-seeding)
smoothMotion = config.getboolean('timelapse', 'smoothMotion', fallback=True)
deflicker = config.getboolean('timelapse', 'deflicker', fallback=True)
ffmpeg1 = str(config['timelapse']['ffmpeg1'])
ffmpeg2 = str(config['timelapse']['ffmpeg2'])
ffmpeg3 = str(config['timelapse']['ffmpeg3'])

isFTP = str(config['ftp']['isFTP'])=='True'
FTP_server = str(config['ftp']['FTP_server'])
FTP_login = str(config['ftp']['FTP_login'])
FTP_pass = str(config['ftp']['FTP_pass'])
FTP_uploadFolder = str(config['ftp']['FTP_uploadFolder'])
FTP_fileNameTimelapse = str(config['ftp']['FTP_fileNameTimelapseMP4'])

tz = timezone(time_zone)
x = datetime.datetime.now(tz)

def buildVideoFilter():
    # scale uses lanczos rather than ffmpeg's default bilinear - it preserves
    # small point sources (stars) better under resize. smoothMotion uses a
    # plain tblend average (no framestep - keeps frame count/duration
    # unchanged) rather than motion-compensated interpolation (minterpolate):
    # true motion estimation is too slow for a Pi over hundreds of frames and
    # tends to ghost/warp on noisy, low-contrast starfields anyway.
    filters = ["scale=" + str(tl_horiz) + ":" + str(tl_vert) + ":flags=lanczos"]
    if smoothMotion:
       filters.append("tblend=average")
    if deflicker:
       filters.append("deflicker=mode=am:size=5")
    return ",".join(filters)


def launchFFmpeg(inputFile, outputFile):

    myOutput = outputFile

    comando = "ffmpeg -framerate "
    comando += framerate
    comando += ' -pattern_type glob -i "'
    comando += inputFile + ".jpg"
    comando += '" -y -vf "'
    comando += buildVideoFilter()
    comando += '"'
    comando += " " + ffmpeg1
    # NOTE: ffmpeg2/ffmpeg3 are appended as-is (expert use) - if they also
    # set -vf/-filter:v, ffmpeg will error out on the duplicate flag; disable
    # smoothMotion/deflicker in config.txt first if you need full control here
    comando += " " + ffmpeg2
    comando += " " + ffmpeg3

    comando += " " + outputFile

    try:
       print(comando)
       os.system(comando)
    except:
       myOutput = ""

    return myOutput


def getTimelapseOutputFileName(today, type):
    valori = ["","",""]
    giorno =  (today+datetime.timedelta(days=-1)).strftime("%Y%m%d")
    tl_folder   = outputFolder + "/" + giorno
    tl_filename = "timelapse_" + giorno
    if type == "TL":
       tl_extension = "_night.mp4"
    else:
       tl_extension = "_24h.mp4"

    tl_filename =  "timelapse_" + giorno + tl_extension

    valori[0] = tl_folder
    valori[1] = tl_filename
    valori[2] = tl_extension
    return valori


def generateTimeLapse(tl_type):
   x = datetime.datetime.now(tz)
   tl_output = getTimelapseOutputFileName(x, tl_type)
   tl_folder = str(tl_output[0])
   tl_filename = str(tl_output[1])
   tl_extension = str(tl_output[2])

   nomeFile = tl_folder + "/" + tl_filename
   # anchored to the "skycam_" capture prefix so startrail_*.jpg (and any
   # other non-capture file dropped in the same day folder) is never globbed in
   inputFile = tl_folder + '/skycam_*' + tl_type

   outputFile = launchFFmpeg(inputFile, nomeFile)
   print(outputFile)

   z=datetime.datetime.now(tz)
   if outputFile =='':
      print("file encoding failed !")
   else:
      print("file encoded in : " + str(abs(z-x).seconds) +" secs")
   return outputFile


def uploadTimeLapse(sourceFile, type):
   if FTP_fileNameTimelapse !="":
      x=datetime.datetime.now(tz)
      destinationFile = FTP_uploadFolder + "/" + FTP_fileNameTimelapse
      if type == "TL":
         destinationFile +=  "_night.mp4"
      else:
         destinationFile +=  "_24h.mp4"

      print(destinationFile)
      time.sleep(2)
      fileManager.saveToFTP(isFTP, sourceFile,FTP_server,FTP_login,FTP_pass,destinationFile)
      z=datetime.datetime.now(tz)
      print("Upload time: " + str(abs(z-x).seconds) +" secs")


def main():

   x0=datetime.datetime.now(tz)
   print("Execution started at: " +str(x))

   if nightTL:
      output = generateTimeLapse("TL")   #night
      uploadTimeLapse(output, "TL")

   if fullTL:
      output = generateTimeLapse("")     #fullday
      uploadTimeLapse(output,"")

   z=datetime.datetime.now(tz)
   print("Total execution time: " + str(abs(z-x0).seconds) +" secs")

   print("AllSkyCam Timelapse is done.")
   return


if __name__ == "__main__":
    main()




