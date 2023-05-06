import datetime
import time
import traceback
from datetime import datetime, timedelta
from frankAllSkyCam import suncalc2, fileManager
from pytz import timezone
import pytz
import sys
import math
import os
from importlib import resources  # Python 3.7+
from configparser import ConfigParser
import socket


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

full_moon_reduc = float(config['moon']['full_moon_reduc'])
ms_offset = float(config['moon']['ms_offset'])
ms_duration = float(config['moon']['ms_duration'])
mr_offset = float(config['moon']['mr_offset'])
mr_duration = float(config['moon']['mr_duration'])

dd_offset_dawn = float(config['offset']['dawn'])
dd_offset_dusk = float(config['offset']['dusk'])

SQM_LE = str(config['sqm_le']['use_sqm'])
SQM_LE_IP = str(config['sqm_le']['ip_address'])
SQM_LE_PORT = float(config['sqm_le']['port'])
SQM_WRITE_LOG = str(config['sqm_le']['write_log'])
SQM_FOLDER = appPath + str(config['system']['sqmFolder'])

esp_secs = float(config['exposure']['esp_secs'])
esp_dawn_dusk = float(config['exposure']['esp_dawn_dusk'])

def getHeader(datacalcolo):
    isDebug= True          # True will stampa debug info. False, not
    logLevel = 0           # 0 = basic, 1= full
    isLinear= False        # True: linear variation of exposure; False:quadratic
    # end of parameters
    # do not touch below

    isTimeLapse =  True
    sun_factor = 1
    riduzione_lineare = 0
    riduzione_quadratica = 0
    zona = "***"
    try:
       #valori:
       #valori[0] = stringa
       #valori[1] = riduzione_totale
       #valori[2] = isTimeLapse
       #valori[3] = zona
       #valori[4] = "TL"
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

       valori=["",0,False,"","","","","","","","","","","",""]

       tz = timezone(timeZone)
       stampa("Orario attuale = "+str(datacalcolo), isDebug, logLevel, 0)

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


       # Get Moon Rise/Set/Fraction/Phase/exposure reduction
       moonValues = getMoonValues(datacalcolo,isDebug, logLevel)
       moon_reduction = getMoonReduction(datacalcolo,isDebug, logLevel)
    
       moon_rise = moonValues[0]
       moon_set = moonValues[1]
       fr = moonValues[2]
       ph = moonValues[3]

       sqm = '--.--'
       if SQM_LE == 'y':
          sqm = readSQM()

       stampa("suncalc2= "+str(sc), isDebug, logLevel, 1)
       sep = " | "
       stringa = datacalcolo.strftime("%d/%m %H:%M") + sep + "NS " + NS + sep
       stringa += "NE " + NE + sep+ "MR " + moon_rise + sep + "MS " + moon_set + sep + str(int(round(fr*100,0))) + "% | " + ph +' | SQM ' + sqm + ' |'


       stampa(stringa, isDebug, logLevel, 0)

       # offset dawn e dusk 
       dawn = dawn+timedelta(minutes= + dd_offset_dawn)
       dusk = dusk+timedelta(minutes= + dd_offset_dusk)

       if (datacalcolo >= night and datacalcolo <= nightEnd) or (datacalcolo >=nightEnd and datacalcolo>=night) or (datacalcolo <nightEnd and datacalcolo<night):
          # prendo il tempo di posa notturno
          zona = "notte"
          riduzione_lineare = 1
          riduzione_quadratica = 1
          valori[4] = "TL"

       elif datacalcolo < srise  and datacalcolo > dawn:
          zona="pre_alba"

       elif datacalcolo > nightEnd and datacalcolo < dawn:
          #transizione alba
          zona = "alba"
          delta = datacalcolo - nightEnd
          totale = dawn  - nightEnd
          deltaminuti = int(delta.total_seconds() / 60)
          durata = int(totale.total_seconds() / 60)
          riduzione_lineare =  round(1-(deltaminuti/durata),3)
          riduzione_quadratica = riduzioneQuadratica(deltaminuti,durata)
       elif (datacalcolo < dusk and datacalcolo >  sset):
          #prima del tramonto
          zona="pre_tramonto"

       elif (datacalcolo >= dusk and datacalcolo < night):
          #transizione tramonto
          zona="tramonto"
          delta = datacalcolo - dusk
          totale = night -dusk
          deltaminuti = int(delta.total_seconds() / 60)
          durata = int(totale.total_seconds() / 60)
          riduzione_lineare = round(deltaminuti/durata,3)
          riduzione_quadratica = round(1-riduzioneQuadratica(deltaminuti, durata),4)
       else:
          # automatico
          zona="giorno"
          isTimeLapse = False

       if isLinear==True:
          riduzione = riduzione_lineare
       else:
          riduzione = riduzione_quadratica

       if riduzione < 0 or riduzione >1 :
          riduzione = 0


       stampa("Rid. Alba/Tram = "+str(riduzione), isDebug, logLevel, 0)
       stampa("dawn           = "+str(dawn), isDebug, logLevel, 0)
       stampa("dusk           = "+str(dusk), isDebug, logLevel, 0)
       stampa("night          = "+str(night), isDebug, logLevel, 0)
       stampa("nightEnd       = "+str(nightEnd), isDebug, logLevel, 0)
       stampa("nightEndHeader = "+str(nightEndHeader), isDebug, logLevel, 0)

       if zona!="notte":
          # moon_reduction only at night
          moon_reduction=1

       riduzione_totale = round(riduzione * moon_reduction,3)
       stampa("zona = " + zona + " -> RL="+ str(riduzione_lineare) + " -> RQ=" + str(riduzione_quadratica) + " | Riduz.Tot. = " + str(round(riduzione_totale,3)), isDebug, logLevel, 0)

       #stampa("Total Reduction= " + str(round(riduzione_totale,3)), isDebug, logLevel, 0)
       esposizione = 0
       if zona == "notte":
          esposizione = int(esp_secs * 1000000 * riduzione_totale)
       elif zona == "alba" or zona == "tramonto":
          esposizione = int(esp_dawn_dusk * 1000000 * riduzione_totale)
       else:
          esposizione = 0

       e=0

       if SQM_LE == "y":
          e = getSQM()

       if e> 0:
          esposizione = e * 1000000

       stringa += str(round(esposizione/1000000,3))
       valori[0] = datacalcolo.strftime("%d/%m/%y")
       valori[1] = datacalcolo.strftime("%H:%M")
       valori[2] = isTimeLapse
       valori[3] = zona
       #valori[4] = impostato in precedenza
       valori[5] = moon_rise
       valori[6] = moon_set
       valori[7] = str(srise)[11:16]
       valori[8] = str(sset)[11:16]
       valori[9] = NS
       valori[10]= NE
       valori[11]= ph
       valori[12] = str(int(round(fr*100,0)))
       valori[13] = esposizione
       valori[14] = sqm

       #print(valori)

    except Exception as e:
       stampa("type error: " + str(e), isDebug, logLevel, 0)
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

def getMoonReduction(datacalcolo, isDebug, logLevel):
   moon_factor = 1
   luna_sorta = False
   luna_tramontata = False


   # Get moonrise/moonset times
   tz = timezone(timeZone)
   smt = suncalc2.getMoonTimes(datacalcolo, latitude, longitude)
   stampa(str(smt), isDebug, logLevel,1)

   # calcolo frazione luna
   sm = suncalc2.getMoonIllumination(datacalcolo)
   fr = float((str(sm["fraction"]))[0:4])


   # ricalcolo luna pre e post:
   smt_prima = suncalc2.getMoonTimes(datacalcolo+timedelta(days=-1), latitude, longitude)
   smt_dopo  = suncalc2.getMoonTimes(datacalcolo+timedelta(days=1), latitude, longitude)

   try:
      mrise= smt["rise"].astimezone(tz)
      moon_rise = str(mrise)[11:16]
   except:
      mset="--"
      moon_set="--"


   try:
      mset= smt["set"].astimezone(tz)
      moon_set = str(mset)[11:16]
   except:
      mset="--"
      moon_set="--"

   if moon_rise!="--" and moon_set!="--":
      if mrise > mset and datacalcolo > mrise:
         if datacalcolo <=mset:
            # mrise del giorno prima
            mrise= "--"
            moon_rise = "--"
         elif (datacalcolo > mset and datacalcolo < mrise) or (datacalcolo >=mrise):
            # mset del giorno dopo
            mset= "--"
            moon_set="--"

   luna_sorta= False
   if moon_rise == "--":
      luna_sorta = True
   else:
      if datacalcolo > mrise:
         luna_sorta = True

   luna_tramontata = True
   if moon_set == "--":
      luna_tramontata = False
   else:
      if datacalcolo < mset:
         luna_tramontata = False


    #Gestione Riduzione esposizione luna
   try:
      moonRise_factor = 1
      # calcolo riduzione presenza luna
      if moon_rise == "--":
         # applicare la riduzione
         luna_sorta = True
      else:
         #esiste un orario in cui la luna sorge
         dmr = datacalcolo - (mrise+timedelta(minutes= -mr_offset))
         deltamoonrise = int(dmr.total_seconds() / 60)
         if deltamoonrise > 0:
            luna_sorta = True
            if deltamoonrise >= 0 and deltamoonrise < mr_duration:
               # la luna è sorta ed è nel transitorio
               moonRise_factor = round(deltamoonrise/mr_duration,3)
         else:
            #la luna non è ancora sorta
            luna_sorta = False
            moonRise_factor=0
   except Exception as e:
      stampa("errore nel moonRise", isDebug, logLevel, 0)
      stampa("type error: " + str(e), isDebug, logLevel, 0)
      stampa(traceback.format_exc(), isDebug, logLevel, 0)

   try:
      moonSet_factor = 1
      if moon_set =="--":
         # applicare la riduzione
         luna_tramontata = False
      else:
         #esiste una orario di tramonto luna.
         dms = (mset+timedelta(minutes=+ms_offset)) - datacalcolo
         deltamoonset = int(dms.total_seconds() / 60)
         if deltamoonset > 0:
            luna_tramontata = False
            if deltamoonset >= 0 and deltamoonset < ms_duration:
               # la luna tramonta ed è nel transitorio
               moonSet_factor = round((deltamoonset/ms_duration),3)
         else:
            luna_tramontata = True
            moonSet_factor = 0
   except Exception as e:
      stampa("errore nel moonSet", isDebug, logLevel, 0)
      stampa("type error: " + str(e), isDebug, logLevel, 0)
      stampa(traceback.format_exc(), isDebug, logLevel, 0)

   #stampa("Moon is rise   = "+str(luna_sorta), isDebug, logLevel, 0)
   #stampa("Moon is set    = "+str(luna_tramontata), isDebug, logLevel, 0)

   if luna_sorta == True and luna_tramontata == False:
     stampa("full moon red  = "+str(full_moon_reduc), isDebug,logLevel,0)
     stampa("moon fraction  = "+str(fr), isDebug,logLevel,0)
     stampa("moonSet  factor= "+str(moonSet_factor), isDebug,logLevel,0)
     stampa("moonRise factor= "+str(moonRise_factor), isDebug,logLevel,0)

     moon_factor = round(1-(full_moon_reduc * fr * moonSet_factor * moonRise_factor),3)

     # | coeff | frazione | moon_rise | moon_set | tot     | esp
     # |  0.7  |   0,01   |     1     |     1    |  0.007  | 55 *(1-0.007)= 54.61
     # |  0.7  |   0,10   |     1     |     1    |  0.07   | 55 *(1-0.070)= 51.10
     # |  0.7  |   0,30   |     1     |     1    |  0.21   | 55 *(1-0.210)= 43.45
     # |  0.7  |   0,70   |     1     |     1    |  0.49   | 55 *(1-0.490)= 28.05
     # |  0.7  |   1,00   |     1     |     1    |  0.7    | 55 *(1-0.700)= 16.50
     # |  0.7  |   0,30   |     1     |     0,9  |  0.19   | 55 *(1-0.700)= 16.50
     # |  0.7  |   1,00   |     1     |     1    |  0.7    | 55 *(1-0.700)= 16.50
   else:
     # moon not visible, so no reduction
     moon_factor = 1

   stampa("Total Moon reduction (1=no reduction)= "+str(moon_factor), isDebug, logLevel, 0)

   return moon_factor


def riduzioneQuadratica(deltaminuti, durata):
    #riduzione_quadratica = round(math.exp(-(deltaminuti**2)/(2*(durata/3)**2))  ,4)
    rid =  math.exp(-(deltaminuti**2)/(2*(durata/3)**2))
    return rid

def stampa(stringa, isDebug, logLevel, logActual):
    if isDebug==False:
        return
    if logLevel>=logActual:
        print("   " + stringa)
    return

def readSQM():
    sqm = '--.--'
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        #print(SQM_LE_IP + ":" + str(int(SQM_LE_PORT)))
        s.connect((SQM_LE_IP,int(SQM_LE_PORT)))
        #print('connected')
        s.sendall(b'rx')
        msg = ''
        while len(msg) < 55:
          chunk = s.recv(55-len(msg))
          if chunk == '':
             print("socket connection broken")
          msg = msg + str(chunk)
        #print(msg)
        sqm=msg[5:10]
        #print(sqm)
        s.close()
        if SQM_WRITE_LOG=='y':
            if int(sqm[0:2]) > 0:
                tz = timezone(timeZone)
                d = datetime.now(tz)
                line = d.strftime("%d/%m/%Y %H:%M") + "," + sqm + "\n"
                f = open(SQM_FOLDER + "/sqm.csv", "a+")
                f.write(line)
                f.close()
    except:
        print('aaa')
    return sqm

def getSQM():
   try:
      s = float(readSQM())
   except:
      print("SQM: Error Reading SQM. Assuming no SMQ Reader")
      s = 0


   if s <= 11:
      e = 0
   elif s >11 and s <= 12:
      e= 0.04
   elif s > 12 and s <= 13:
      e = 0.07
   elif s > 13 and s <= 14:
      e = 0.20
   elif s > 14 and s <= 15:
      e = 0.70
   elif s > 15 and s <= 16:
      e = 1.00
   elif s > 16 and s <= 17:
      e = 1.75
   elif s > 17 and s <= 18:
      e = 3.00
   elif s > 18 and s <= 19:
      e = 15
   elif s > 19 and s <= 20:
      e = 30
   elif s > 20  and s <= 21:
      e = 45
   elif s > 20  and s <= 22:
      e = 75
   else:
      e= 0

   ec = 0
   if s > 10.5:
      ec = round((2.84**s/((s**2)*80000)),2)

   if ec > esp_secs:
      ec = esp_secs

   stampa("SQM: " + str(s) + ", > calc exposure, SQM exposure = ," + str(e) + "," + str(ec) , True, 5,0)

   return  ec

