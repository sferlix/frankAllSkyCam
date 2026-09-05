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
    genExtraDataFile = homePath + "/frankAllSkyCam/tools/generateExtraData.py"
    toolsConfigFile = homePath + "/frankAllSkyCam/tools/generateExtraData.conf"

    if not os.path.isfile(fileName):
       #ensure folders do exist only if config.txt is not existing
       createAppFolders()

    # every package-bundled seed template lives under defaults/, not loose
    # among the .py files - so nothing in site-packages can be mistaken for
    # the live copy (what every module actually reads/uses at runtime)
    checkFile(fileName, "/defaults/config.txt")
    checkFile(htmlFile, "/defaults/tools/index.html")
    checkFile(sqmExpCsv, "/defaults/sqmexp.csv")
    checkFile(moonFile, "/defaults/png/moon.png")
    checkFile(logoFile, "/defaults/png/logo.png")
    checkFile(compFile, "/defaults/png/compass.png")
    checkFile(jupiterFile, "/defaults/png/jupiter.png")
    checkFile(marsFile, "/defaults/png/mars.png")
    checkFile(saturnFile, "/defaults/png/saturn.png")
    checkFile(venusFile, "/defaults/png/venus.png")
    checkFile(phaseFile, "/defaults/png/moon.png")
    # seeded only if missing, so a user's own edits survive package upgrades
    checkFile(genExtraDataFile, "/defaults/tools/generateExtraData.py")
    checkFile(toolsConfigFile, "/defaults/tools/generateExtraData.conf")

    return fileName

def checkFile(destFileName, sourceFileName):
    if not os.path.isfile(destFileName):
       # ensure the destination's directory exists - matters for files seeded
       # into a subfolder (e.g. tools/) added after the initial install, when
       # createAppFolders() (fresh-install only) never runs again
       destDir = os.path.dirname(destFileName)
       if destDir and not os.path.isdir(destDir):
          createPath(destDir)
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
    toolsDir = createPath(homePath + "/frankAllSkyCam/tools")
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


