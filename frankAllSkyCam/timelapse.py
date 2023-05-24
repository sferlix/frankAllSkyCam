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

def launchFFmpeg(inputFile, outputFile):

    myOutput = outputFile
    if outputFile[-7:]=="24h.mp4":
       extension="*.jpg"
    else:
       extension="*TL.jpg"

#' -vf "tblend=average,framestep=2,tblend=average,framestep=2,tblend=average,framestep=2,tblend=average,framestep=2,setpts=0.25*PTS" '
#" -filter:v minterpolate"
#" -c:v libx264 -crf 12 -preset slow -pix_fmt yuv420p "

    comando = "ffmpeg -framerate "
    comando += framerate
    comando += ' -pattern_type glob -i "'
    comando += inputFile + ".jpg"
    comando += '" -y -s:v '
    comando += str(tl_horiz) +"x" + str(tl_vert)
    comando += " " + ffmpeg1
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
   inputFile = tl_folder + '/*' + tl_type

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




