'''
 this file calculates the exposure basing on SQM
 it requires the model stored in sqmexp.csv
 you can personalize the model by editing the above file
'''

import numpy
import csv
import sys
import os


def main(argv):
    if len(argv)==0:
       print("No image file provided !\n Usage:\n python3 exposurecalc.py <sqm_value>")
       return

    sqm_value = float(argv[0])
    ret = getExposure(sqm_value)

    print("SQM: " + str(sqm_value) + " => Exposure (secs): " + str(ret))
    return

def getExposure(sq, esp_secs=None, appPath=None):
   # esp_secs/appPath accepted (and ignored) so this shares an interface with
   # autoexposure.getExposure() - exposure_mode in config.txt picks between them

   if sq < 9:
      # no need to change the exposure.
      return 0

   csvfile = os.path.expanduser("~") + "/frankAllSkyCam/sqmexp.csv"
   sqmVals = []
   expVals = []
   with open(csvfile, newline='') as f:
      reader = csv.DictReader(f)
      for row in reader:
         sqmVals.append(float(row['sqm']))
         expVals.append(float(row['secs']))

   sqmVals = numpy.array(sqmVals)
   expVals = numpy.array(expVals)

   if sq >= 9 and sq <= 17:
      # build polynomial model 1, for SQM < 17
      mask = sqmVals < 17.0
   else:
      # build polynomial model 2, for SQM > 17
      mask = sqmVals >= 17.0

   mySqm = sqmVals[mask]
   myExp = expVals[mask]

   polyGrade = 3
   myModel= numpy.poly1d(numpy.polyfit(mySqm, myExp, polyGrade ))
   ex = round(myModel(sq),4)

   return ex

if __name__ == "__main__": 
   main(sys.argv[1:])

