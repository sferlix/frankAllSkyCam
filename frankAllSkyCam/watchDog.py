'''
 this file controls that everything is fine (check alive.txt)
 in case the file is older than #rebootAfter minutes, it reboots your Pi
 you can configure #rebootAfter in your config.txt
'''

import os.path, time, datetime
from configparser import ConfigParser
from frankAllSkyCam import fileManager
import subprocess


config = ConfigParser()
configFileName = fileManager.getConfigFileName()
config.read(configFileName)
appPath = os.path.expanduser("~") + "/frankAllSkyCam/"

logFolder = appPath + str(config['system']['logFolder'])
myfile = logFolder  + "/alive.txt"

maxMinutes = int(config['system']['rebootAfter'])

def getOutput(command):
   output=subprocess.getoutput(command)
   space = "\n\n\n\n\n"
   return "::::::::::::::::" + command + ":::::::::::::::::: \n\n"+output + space

def main():
  n=datetime.datetime.now()
  f=datetime.datetime.strptime(time.ctime(os.path.getmtime(myfile)), '%c')
  secs = int((n-f).total_seconds())
  minutes = int(secs / 60)
  print(myfile + " created at: %s" % f)
  print("The file is " + str(secs) + " secs old (" + str(minutes) + " minutes)")

  if minutes>maxMinutes:
     print("rebooting...")
     os.system("sudo reboot")
  return

def generateLogs():
    fileManager.createPath(logFolder)
    fileName = logFolder + "/reboot_" + n.strftime("%Y%m%d_%H%M%s")+ ".txt"
    o1=getOutput("sudo vcdbg log assert")
    o2=getOutput("sudo vcdbg log msg")
    o3=getOutput("dmesg")
    o4=getOutput("cat /var/log/messages")
    f = open(fileName, "w")
    f.write(o1+o2+o3+o4)
    f.close()
    return 


if __name__ == "__main__":
    main()

