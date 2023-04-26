import os, numpy
from PIL import Image
import ftplib
import datetime
import time
import os
from pytz import timezone
from os import path
from configparser import ConfigParser
from allskycam import fileManager

config = ConfigParser()
config.read(os.path.join(os.path.dirname(__file__), '', 'config.txt'))
time_zone = str(config['site']['time_zone'])

outputFolder = str(config['system']['otuputFolder'])

isFTP = str(config['ftp']['isFTP'])=='True'
FTP_server = str(config['ftp']['FTP_server'])
FTP_login = str(config['ftp']['FTP_login'])
FTP_pass = str(config['ftp']['FTP_pass'])
FTP_uploadFolder = str(config['ftp']['FTP_uploadFolder'])
FTP_fileNameStarTrail = str(config['ftp']['FTP_fileNameStarTrailJPG'])

tz = timezone(time_zone)
x = datetime.datetime.now(tz)


def launchStarTrail(inputFolder, outputFile):
    try:
        print(inputFolder)
        files = os.listdir(inputFolder)
        images = [name for name in files if name[-6:] in ["TL.jpg", "TL.JPG"]]
        width, height = Image.open(inputFolder+images[0]).size
        stack   = numpy.zeros((height, width, 3), numpy.float)
        counter = 1
        for image in images:
            image_new = numpy.array(Image.open(inputFolder+image), dtype = numpy.float)
            stack     = numpy.maximum(stack, image_new)
            counter  += 1
            print("stacking "+  str(image))

        stack = numpy.array(numpy.round(stack), dtype = numpy.uint8)
        output = Image.fromarray(stack, mode = "RGB")
        output.save(outputFile, "JPEG")
    except:
        myOutput = ""

    return 


def getStarTrailOutputFileName():
    valori = ["",""]
    x = datetime.datetime.now(tz)
    giorno =  (x+datetime.timedelta(days=-1)).strftime("%Y%m%d")
    tl_folder   = outputFolder + "/" + giorno + "/"
    tl_filename =  outputFolder + "/" + giorno + "/startrail_" + giorno + ".jpg"

    valori[0] = tl_folder
    valori[1] = tl_filename
    return valori




def uploadStarTrail(sourceFile):
    if FTP_fileNameStarTrail !="":
       x=datetime.datetime.now(tz)
       print(FTP_uploadFolder + FTP_fileNameStarTrail)
       time.sleep(2)
       fileManager.saveToFTP(isFTP, sourceFile,FTP_server,FTP_login,FTP_pass,FTP_uploadFolder + FTP_fileNameStarTrail)
       z=datetime.datetime.now(tz)
       print("Upload time: " + str(abs(z-x).seconds) +" secs")


def main():

    x0=datetime.datetime.now(tz)
    print("Execution started at: " +str(x))

    output = getStarTrailOutputFileName()
    inputFolder = output[0] 
    outputFile  = output[1]
    print(output)

    launchStarTrail(inputFolder,outputFile)
    uploadStarTrail(outputFile)


    z=datetime.datetime.now(tz)
    print("Total execution time: " + str(abs(z-x0).seconds) +" secs")

    print("AllSkyCam startrail is done.")
    return


if __name__ == "__main__":
    main()


