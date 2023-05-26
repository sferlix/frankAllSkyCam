'''
 this file contains the code to calculate astronomical events
 and other info that will be printed on the jpg file
'''

import datetime
import time
import traceback
from datetime import datetime, timedelta
from frankAllSkyCam import suncalc2, fileManager
from frankAllSkyCam import sqmreader, exposurecalc
from pytz import timezone
import pytz
import sys
import math
import os
from importlib import resources  # Python 3.7+
from configparser import ConfigParser
import socket
import numpy
import pandas

config = ConfigParser()
configFileName = fileManager.getConfigFileName()
config.read(configFileName)
appPath = os.path.expanduser("~") + "/frankAllSkyCam/"

time_zone = str(config['site']['time_zone'])
inte = str(config['site']['inte'])

logFolder = appPath + str(config['system']['logFolder'])
outputFolder = appPath + str(config['system']['otuputFolder'])

latitude  = float(config['site']['latitude'])
longitude = float(config['site']['longitude'])
timeZone = str(config['site']['time_zone'])

dd_offset_dawn = float(config['offset']['dawn'])
dd_offset_dusk = float(config['offset']['dusk'])

esp_secs = float(config['exposure']['esp_secs'])

def getHeader(datacalcolo):
    isDebug= True          # True will stampa debug info. False, not
    logLevel = 0           # 0 = basic, 1= full
    isLinear= False        # True: linear variation of exposure; False:quadratic
    # end of parameters
    # do not touch below

    isTimeLapse =  True
    sun_factor = 1
    zona = "***"
    try:
       #valori:
       #valori[0] = stringa
       #valori[1] = riduzione_totale
       #valori[2] = isTimeLapse
       #valori[3] = zona
       #valori[4] = filename suffix
       #valori[5] = moonrise
       #valori[6] = moonset
       #valori[7] = sunrise
       #valori[8] = sunset
       #valori[9] = nightstart
       #valori[10]= nightend
       #valori[11]= moonphase
       #valori[12] = moonangle
       #valori[13] = exposure
       #valori[14] = sqm

       valori=["",0,False,"","","","","","","","","","",0,0]

       tz = timezone(timeZone)
       stampa("Now            = "+str(datacalcolo), isDebug, logLevel, 0)

       # get sun information
       sc = suncalc2.getTimes(datacalcolo, latitude, longitude)

       s_set  = datetime.strptime(sc["sunset"],"%Y-%m-%d %H:%M:%S")
       dusk_ = datetime.strptime(sc["dusk"],"%Y-%m-%d %H:%M:%S")
       night_ = datetime.strptime(sc["night"],"%Y-%m-%d %H:%M:%S")
       nightEnd_ = datetime.strptime(sc["nightEnd"],"%Y-%m-%d %H:%M:%S")
       dawn_ = datetime.strptime(sc["dawn"],"%Y-%m-%d %H:%M:%S")
       s_rise = datetime.strptime(sc["sunrise"],"%Y-%m-%d %H:%M:%S")

       dawn = dawn_.astimezone(tz)
       srise  = s_rise.astimezone(tz)
       sset   = s_set.astimezone(tz)
       dusk = dusk_.astimezone(tz)
       night = night_.astimezone(tz)
       nightEnd = nightEnd_.astimezone(tz)

       sc2 = suncalc2.getTimes(datacalcolo+timedelta(days=1), latitude, longitude)

       # dopo il tramonto, calcolo alba e tramonto del giorno dopo
       if datacalcolo > sset:
          s_set_ = datetime.strptime(sc2["sunset"],"%Y-%m-%d %H:%M:%S")
          sset = s_set_.astimezone(tz)
          s_rise_ = datetime.strptime(sc2["sunrise"],"%Y-%m-%d %H:%M:%S")
          srise = s_rise_.astimezone(tz)

       # dopo fine notte, calcolo il nightEnd del giorno dopo
       if datacalcolo > nightEnd:
          nightEndH_ = datetime.strptime(sc2["nightEnd"],"%Y-%m-%d %H:%M:%S")
          nightEndHeader = nightEndH_.astimezone(tz)
       else:
          nightEndHeader = nightEnd_.astimezone(tz)

       NS = str(night)[11:16]
       NE = str(nightEndHeader)[11:16]


       # Get Moon Rise/Set/Fraction/Phase
       moonValues = getMoonValues(datacalcolo,isDebug, logLevel)

       moon_rise = moonValues[0]
       moon_set = moonValues[1]
       fr = moonValues[2]
       ph = moonValues[3]

       # offset dawn e dusk
       dawn = dawn+timedelta(minutes= + dd_offset_dawn)
       dusk = dusk+timedelta(minutes= + dd_offset_dusk)

       esposizione = 0
       lett = getSQM()
       e= lett[0]
       sqm= lett[1]
       if e> 0:
          esposizione = int(e * 1000000)

       suffisso = ""
       if (datacalcolo >= night and datacalcolo <= nightEnd) or (datacalcolo >=nightEnd and datacalcolo>=night) or (datacalcolo <nightEnd and datacalcolo<night):
          # prendo il tempo di posa notturno 0
          zona = "night"
          suffisso = "YTL"  # YES, create startrails for stars in this timeframe
       elif datacalcolo < srise  and datacalcolo > dawn and datacalcolo < nightEnd:
          zona="dawn to day"   # no timelapse, no startrails
       elif datacalcolo > nightEnd and datacalcolo < dawn:
          zona = "night to dawn"
          suffisso = "NTL"  #no startrails but yes night Timelapse
       elif (datacalcolo < dusk and datacalcolo >  sset):
          zona="sset to dusk"
       elif (datacalcolo >= dusk and datacalcolo < night):
          suffisso = "NTL"  #no startrails but yes night Timelapse
          zona="dusk to night"
       else:
          zona="day"
          isTimeLapse = False

       valori[0] = datacalcolo.strftime("%d/%m/%y")
       valori[1] = datacalcolo.strftime("%H:%M")
       valori[2] = isTimeLapse
       valori[3] = zona
       valori[4] = suffisso
       valori[5] = moon_rise
       valori[6] = moon_set
       valori[7] = str(srise)[11:16]
       valori[8] = str(sset)[11:16]
       valori[9] = NS
       valori[10]= NE
       valori[11]= ph
       valori[12]= str(int(round(fr*100,0)))
       valori[13]= esposizione
       valori[14]= sqm

       stampa("Dawn       = "+str(dawn), isDebug, logLevel, 0)
       stampa("SunRise    = "+str(srise), isDebug, logLevel, 0)
       stampa("SunSet     = "+str(sset), isDebug, logLevel, 0)
       stampa("Dusk       = "+str(dusk), isDebug, logLevel, 0)
       stampa("Night      = "+str(night), isDebug, logLevel, 0)
       stampa("NightEnd   = "+str(nightEnd), isDebug, logLevel, 0)
       stampa("Zone       = " + zona, isDebug, logLevel, 0)
       stampa("SQM        = " + str(sqm), isDebug, logLevel, 0)
       stampa("Exopsure   = " + str(esposizione), isDebug, logLevel, 0)

    except Exception as e:
       stampa(traceback.format_exc(), isDebug, logLevel, 0)
       valori[0] = ""
       valori[1] = 0
    return valori


def getMoonValues(datacalcolo, isDebug, logLevel):
   moon_factor = 1
   #Get moon illumination information
   sm = suncalc2.getMoonIllumination(datacalcolo)
   mf = float(sm["phase"])
   an = float(sm["angle"])
   fr = float((str(sm["fraction"]))[0:4])

   moon_phase=str(mf)[0:5]
   stampa("Moon phase     = " + str(mf) + " | Moon angle     = " + str(an) + " | Moon fraction  = " + str(fr), isDebug, logLevel, 1)

   # Get moonrise/moonset times
   tz = timezone(timeZone)
   smt = suncalc2.getMoonTimes(datacalcolo, latitude, longitude)
   stampa(str(smt), isDebug, logLevel,1)

   # calcolo luna pre e post:
   smt_prima = suncalc2.getMoonTimes(datacalcolo+timedelta(days=-1), latitude, longitude)
   smt_dopo  = suncalc2.getMoonTimes(datacalcolo+timedelta(days=1), latitude, longitude)
   isPresente = False

   try:
      mrise= smt["rise"].astimezone(tz)
      moon_rise = str(mrise)[11:16]
   except:
      mrise= smt_dopo["rise"].astimezone(tz)
      moon_rise = str(mrise)[11:16] + "+1"


   try:
      mset= smt["set"].astimezone(tz)
      moon_set = str(mset)[11:16]
   except:
      mset= smt_dopo["set"].astimezone(tz)
      moon_set = str(mset)[11:16] + "+1"

   if mset < mrise:
      if  datacalcolo < mset:
          isPresente = True
      if  datacalcolo > mset:
          isPresente = False
          mset= smt_dopo["set"].astimezone(tz)
          moon_set = str(mset)[11:16]+ "+1"

   if (datacalcolo > mrise and datacalcolo < mset):
      isPresente = True


   #calculating phase
   ph = ""
   if mf>=0.86 or  mf<0.12:
      ph = "New"
   elif mf>=0.12  and mf<0.21:
        ph = "WaxCr"
   elif mf>=0.21  and mf<0.32:
        ph = "1st Q"
   elif mf>=0.32  and mf<0.39:
        ph = "WaxGib"
   elif mf>=0.37  and mf<0.62:
        ph = "Full"
   elif mf>=0.62  and mf<0.69:
        ph = "WanGib"
   elif mf>=0.69 and mf<0.78:
        ph = "Last Q"
   elif mf>=0.78 and mf<=0.88:
        ph = "WanCr"

   stampa("Moon rise      = " + str(mrise) + " | " + moon_rise, isDebug, logLevel, 0)
   stampa("Moon set       = " + str(mset) + " | " + moon_set, isDebug, logLevel, 0)
   stampa("Moon Phase     = " + ph, isDebug, logLevel, 0)
   stampa("Moon Angle     = " + str(fr)+"%", isDebug, logLevel, 0)
   stampa("Moon Present   = " + str(isPresente), isDebug, logLevel, 0)

   valori=["","",0,""]
   valori[0] = moon_rise
   valori[1] = moon_set
   valori[2] = fr
   valori[3] = ph

   return valori


def stampa(stringa, isDebug, logLevel, logActual):
    if isDebug==False:
        return
    if logLevel>=logActual:
        print("   " + stringa)
    return

def getSQM():
   ex=0
   sq=0
   r= [ex,sq]

   try:
      sq = sqmreader.readSQM()
   except:
      stampa("type error: " + str(e), isDebug, logLevel, 0)
      stampa(traceback.format_exc(), isDebug, logLevel, 0)
      print("imageHeader.getSQM: Error while calculating SQM")

   if sq < 9:
      r=[ex,sq]
      # no need to change the exposure.
      return r

   ex = exposurecalc.getExposure(sq)

   #max exposure (esp_secs from config.txt) wins over the calculated exposure
   if ex>esp_secs:
      ex = esp_secs

   r=[ex,sq]
   return r
