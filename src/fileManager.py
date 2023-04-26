import ftplib
import datetime
import time
import os

from os import path

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
        print("ERROR while copyng file " + nomefile + " to  " + outputLocalWebFile)
        print("ERROR: " + str(sys.exc_info()[0]))



