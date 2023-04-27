import os.path, time, datetime
from configparser import ConfigParser
from frankAllSkyCam import fileManager
import subprocess

config = ConfigParser()
config.read(os.path.expanduser("~")+"/frankAllSkyCam/config.txt")
logFolder = str(config['system']['logFolder'])
myfile = str(config['system']['outputLocalWebFile'])
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
     fileManager.createPath(logFolder)
     fileName = logFolder + "/reboot_" + n.strftime("%Y%m%d_%H%M%s")+ ".txt"
     o1=getOutput("sudo vcdbg log assert")
     o2=getOutput("sudo vcdbg log msg")
     o3=getOutput("dmesg")
     o4=getOutput("cat /var/log/messages")
     f = open(fileName, "w")
     f.write(o1+o2+o3+o4)
     f.close()
     print("rebooting...")
     os.system("sudo reboot")
  return

if __name__ == "__main__":
    main()

