'''
 file management, creation of folders, FTP client
'''

import ftplib
import datetime
import time
import os
from os import path
#from frankAllSkyCam import calculateEphem

def saveToFTP(isFTP,nomefile,FTP_server,FTP_login,FTP_pass,FTP_fileName):
   if not isFTP:
      return

   try:
      print("Transferring " + nomefile + " to FTP: " + FTP_server + FTP_fileName + " ....")
      session = ftplib.FTP(FTP_server,FTP_login,FTP_pass)
      file = open(nomefile,'rb')
      session.storbinary("STOR " + FTP_fileName, file)
      file.close()
      session.quit()
      pass
   except:
      print("FTP ERROR")


def createPath(dir):
   x = dir.split("/")
   l = len(x)
   d=""
   ret = False
   for i in range(0,l):
     d +=  x[i] +"/"
     if not path.exists(d):
        print(d + " does not exists.")
        try:
           os.mkdir(d)
           print("New folder created: " + d)
        except OSError:
           print("error when creating folder: " + d)
           print("output folder assumed = " + d)
     else:
        print(d + " exists.")
   if path.exists(dir):
      ret = True
   return ret

def getConfigFileName():
    homePath = os.path.expanduser("~")
    fileName = homePath + "/frankAllSkyCam/config.txt"
    htmlFile = homePath + "/frankAllSkyCam/index.html"
    sqmExpCsv= homePath + "/frankAllSkyCam/sqmexp.csv"
    moonFile = homePath + "/frankAllSkyCam/png/moon.png"
    logoFile = homePath + "/frankAllSkyCam/png/logo.png"
    compFile = homePath + "/frankAllSkyCam/png/compass.png"
    phaseFile= homePath + "/frankAllSkyCam/png/phase.png"
    jupiterFile= homePath + "/frankAllSkyCam/png/jupiter.png"
    saturnFile= homePath + "/frankAllSkyCam/png/saturn.png"
    marsFile= homePath + "/frankAllSkyCam/png/mars.png"
    venusFile= homePath + "/frankAllSkyCam/png/venus.png"

    if not os.path.isfile(fileName):
       #ensure folders do exist only if config.txt is not existing
       createAppFolders()

    checkFile(fileName, "/config.txt")
    checkFile(htmlFile, "/index.html")
    checkFile(sqmExpCsv, "/sqmexp.csv")
    checkFile(moonFile, "/moon.png")
    checkFile(logoFile, "/logo.png")
    checkFile(compFile, "/compass.png")
    checkFile(jupiterFile, "/jupiter.png")
    checkFile(marsFile, "/compass.png")
    checkFile(saturnFile, "/saturn.png")
    checkFile(venusFile, "/venus.png")
    checkFile(phaseFile, "/moon.png")

    return fileName

def checkFile(destFileName, sourceFileName):
    if not os.path.isfile(destFileName):
       cfd = os.path.dirname(os.path.realpath(__file__))
       copyFile(cfd + sourceFileName, destFileName)

def copyFile(origin, dest):
    try:
       print("copying " + origin + " file to " + dest + " ...")
       os.system("cp " + origin + " " + dest)
    except:
       print("ERROR while copying file " + origin + " to " + dest)
       fileName = ""
    return

def createAppFolders():
    homePath = os.path.expanduser("~")
    appDir = createPath(homePath + "/frankAllSkyCam")
    logDir = createPath(homePath + "/frankAllSkyCam/log")
    imgDir = createPath(homePath + "/frankAllSkyCam/img")
    smqDir = createPath(homePath + "/frankAllSkyCam/sqm")
    smqDir = createPath(homePath + "/frankAllSkyCam/png")
    return

def getOutputFileName(outputDir, today):
   # this method returns output file name, including full path

   if not path.exists(outputDir):
      print("WARNING Folder does not exist. Attempt to create: " + outputDir)
      createPath(outputDir)

   if today.hour >= 8:
     outDir = outputDir + "/" + today.strftime("%Y%m%d")
   else:
     outDir = outputDir + "/" + (today+datetime.timedelta(days=-1)).strftime("%Y%m%d")

   if not path.exists(outDir):
      # create  folder
      try:
         os.mkdir(outDir)
         print("New output folder created: " + outDir)
      except OSError:
         print("error when creating folder: " + outDir)
         print("output folder assumed = " + outputDir)
         outDir = outputDir

   fileName = outDir+"/skycam_" + today.strftime("%Y%m%d_%H%M%s")
   return fileName


def saveToWEB(nomefile, outputLocalWebFile):
   if outputLocalWebFile !="":
      #copying in web folder
      try:
        print("Copying in web folder: " + outputLocalWebFile + " ...")
        os.system("sudo cp " + nomefile + " " + outputLocalWebFile)
      except:
        print("ERROR while copying file " + nomefile + " to  " + outputLocalWebFile)
        print("ERROR: " + str(sys.exc_info()[0]))

   return


