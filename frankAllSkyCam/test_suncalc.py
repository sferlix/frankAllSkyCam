import os
import sys
from configparser import ConfigParser
import datetime
from datetime import timedelta
from fractions import Fraction
import time
from pytz import timezone
import pytz
from allskycam import imageHeader, fileManager

# Read configuration from config file
config = ConfigParser()
configFileName = fileManager.getConfigFileName()
config.read(configFileName)


time_zone = str(config['site']['time_zone'])
esp_secs = float(config['exposure']['esp_secs'])
esp_dawn_dusk = float(config['exposure']['esp_dawn_dusk'])
tz = timezone(time_zone)



def testQuadratico(durata, intervallo):
    durata = 40
    for x in range(durata):
      s = riduzioneQuadratica(x, durata)
      t = riduzioneQuadratica2(x, durata)
      print("elapsed:" + str(x) + " | durata:" + str(durata) +" | " + "rid:" + str(s) + " | " + str(s*55)+" | " + "rid:" + str(t) + " | " + str(t*55))
    return

def testPath(txt):
   fileManager.createPath(txt)
   return

def testEsposizioni(startDate, durata, intervallo):

   iterazioni = int(durata * 60 /intervallo) +1
   d2 = tz.localize(startDate)
   os.system("clear")
   print("initial date: " +str(d2))
   print("=========================================")

   for x in range(iterazioni):
      print("| " +str(x) + " |=========================================")
      s = imageHeader.getHeader(d2)
      header = str(s[0])
      isNotte = s[1]
      zona = s[3]
      if zona == "notte":
         esposizione = (esp_secs * isNotte)
         print("Exposure: "+ zona + " -> " + str(esp_secs) + " -> "  + str(round(esposizione,2)))
      elif zona == "alba" or zona == "tramonto":
         esposizione = (esp_dawn_dusk * isNotte)
         print("Exposure: "+ zona + " -> " + str(esp_dawn_dusk) + " -> "  + str(round(esposizione,2)))
      else:
         esposizione = 0
         print("Exposure: " + zona + " -> " + str(0) + " -> "  + str(round(esposizione,2)))
      d2 = d2+timedelta(minutes=intervallo)

   print("final date: " +str(d2))
   return

def main():
   d = datetime.datetime(2021, 5, 30, 21,35 , 10)
   #d = datetime.datetime.now(tz)

   durata     = 2   # ore
   intervallo = 1.5      # minuti
   #testEsposizioni(d, durata, intervallo)
   testPath("/home/pi/asc/img")

   return


if __name__ == "__main__":
    main()


