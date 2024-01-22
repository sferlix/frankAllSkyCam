'''
 this file calculates the exposure basing on SQM
 it requires the model stored in sqmexp.csv
 you can personalize the model by editing the above file
'''

import numpy
import pandas
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

def getExposure(sq):

   csvfile = os.path.expanduser("~") + "/frankAllSkyCam/sqmexp.csv"
   df0 = pandas.read_csv(csvfile)

   if sq < 9:
      # no need to change the exposure.
      return 0
   elif sq >= 9 and sq <= 17:
      # build polynomial model 1, for SQM < 17
      df0 = df0[df0.sqm < 17.0]
   else:
      # build polynomial model 2, for SQM > 17
      df0 = df0[df0.sqm >= 17.0]

   EXP = df0['secs']
   SQM = df0['sqm']
   myExp = EXP.values
   mySqm = SQM.values

   polyGrade = 3
   myModel= numpy.poly1d(numpy.polyfit(mySqm, myExp, polyGrade ))
   ex = round(myModel(sq),4)

   return ex

if __name__ == "__main__": 
   main(sys.argv[1:])

