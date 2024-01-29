#!/usr/bin/python3

import ephem  #pip3 install ephem
import math   #sudo apt-get install libmagickwand-dev
import pytz
import sys
import os
import datetime
from frankAllSkyCam import fileManager
from datetime import datetime,date, timezone
from wand.image import Image
from wand.drawing import Drawing
from wand.color import Color
from configparser import ConfigParser
import bisect

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
elevation = float(config['site']['elevation'])

timeZone = str(config['site']['time_zone'])

moonpath = "moon.png" #Input (full moon) image file path
phasepath = "/home/pi/frankAllSkyCam/phase.png" #Output image file path
textpath = "moon.txt" # Output text file path
myTimezone = "Europe/Rome"
elevation = int('1000')

DAY = 1.0/29.33
MOONPHASE = [
    (0.0/4.0 + DAY, 'New'),
    (1.0/4.0 - DAY, 'Waxing Cr'),
    (1.0/4.0 + DAY, '1st Q'),
    (2.0/4.0 - DAY, 'Waxing Gib'),
    (2.0/4.0 + DAY, 'Full'),
    (3.0/4.0 - DAY, 'Waning Gib'),
    (3.0/4.0 + DAY, 'Last Q'),
    (4.0/4.0 - DAY, 'Waning Cr'),
    (4.0/4.0,       'New'),
]
RANGES = [x[0] for x in MOONPHASE]


def calculate(dt):
   tz = pytz.timezone("utc")
   mytz = pytz.timezone(myTimezone)
   dt = dt.astimezone(tz)

   mySite = ephem.Observer()
   mySite.lon = latitude
   mySite.lat = longitude
   mySite.elevation = elevation
   mySite.date = dt

   print("Now:" + str(dt))
   sun = ephem.Sun()
   moon = ephem.Moon()

   moon.compute(mySite)
   moon_setting = mySite.next_setting(ephem.Moon()).datetime()
   moon_next_new = (ephem.next_new_moon(mySite.date)).datetime()

   
   phase = moon.moon_phase
   mp = moon.moon_phase
   a = moon.elong
   mp = 1 - mp
   if a > 0:
       mp = -mp

   moonAlt = float(moon.alt)*180/ephem.pi
   if moonAlt < 0.:
      moon_next_rising = mySite.next_rising(moon)
   else:
      moon_next_rising = mySite.previous_rising(moon)

   moon_next_rising = moon_next_rising.datetime()
   moon_next_rising = tz.localize(moon_next_rising)
   moon_next_rising = moon_next_rising.astimezone(mytz)

   moon_setting = tz.localize(moon_setting)
   moon_Setting = moon_setting.astimezone(mytz)

   mr = moon_next_rising.strftime("%H:%M")
   if (-dt.day + moon_next_rising.day) != 0: mr=mr +  "%+d" % int(moon_next_rising.day-dt.day)

   ms = moon_setting.strftime("%H:%M")
   if (-dt.day + moon_setting.day) != 0: ms=ms +  "%+d" % int(moon_setting.day-dt.day)

   nm = moon_next_new.strftime("%d %b")

   sun.compute(mySite)
   sunAlt = float(sun.alt)*180/ephem.pi

   sunSet = mySite.next_setting(ephem.Sun(), use_center=True).datetime()
   if sunAlt < -18.:
      sunRise = mySite.next_rising(ephem.Sun(), use_center=True).datetime()
      sf = "YTL"   #yes timelapse, yes startrail
   elif sunAlt >= -18. and sunAlt < 0.:
      sunRise = mySite.next_rising(ephem.Sun(), use_center=True).datetime()
      sf = "NTL"  #yes timelapse, no startrail
   else:
      sunRise = mySite.previous_rising(ephem.Sun(), use_center=True).datetime()
      sf = ""    #no timelapse, no startrail

   mySite.horizon =  '-18'  #astronomic twilight
   nightEnd = mySite.next_rising(ephem.Sun(), use_center=True).datetime()

   if sunAlt >  -18.:
      nightStart = mySite.next_setting(ephem.Sun(), use_center=True).datetime()
   else:
      nightStart = mySite.previous_setting(ephem.Sun(), use_center=True).datetime()

   #localization
   sRise = tz.localize(sunRise)
   sSet = tz.localize(sunSet)
   nStart = tz.localize(nightStart)
   nEnd = tz.localize(nightEnd)

   sRise = sRise.astimezone(mytz)
   sSet = sSet.astimezone(mytz)
   nStart = nStart.astimezone(mytz)
   nEnd = nEnd.astimezone(mytz)

   # string management
   sr = sRise.strftime("%H:%M")
   if (dt.day - sRise.day) != 0: sr=sr + "%+d" % int(sRise.day-dt.day)

   ss = sSet.strftime("%H:%M")
   if (dt.day - sSet.day) != 0: ss=ss + "%+d" % int(sSet.day-dt.day)

   ns = nStart.strftime("%H:%M")
   if (dt.day - nStart.day) != 0: ns=ns + "%+d" % int(nStart.day-dt.day)

   ne = nEnd.strftime("%H:%M")
   if (dt.day - nEnd.day) != 0: ne=ne + "%+d" % int(nEnd.day-dt.day)

   moonPhase = str(int(phase*100))+"%"

   lunation = get_phase_on_day(ephem.now().datetime())
   lun_phase = bisect.bisect_right(RANGES, lunation)
   human_phase= MOONPHASE[lun_phase][1]


   data = {
      "data": dt.strftime("%d/%m/%y"),
      "ora": dt.astimezone(mytz).strftime("%H:%M"),
      "isTimelapse": (sf == "YTL" or sf == "NTL"),
      "suffisso": sf,
      "moonRise": mr,
      "moonSet": ms,
      "newMoon": nm,
      "sunRise": sr,
      "sunSet": ss,
      "nightStart": ns,
      "nightEnd": ne,
      "moonPhase": str(int(phase*100))+"% - " + human_phase,
      "mp": mp
      }
   return data

def generateMoonImage(phase, phasepath):
    #Draw phase shade on input moon image and save
    with Image(filename=moonpath) as img:
        radius = img.height // 2
        with Drawing() as draw:
            draw.fill_color = Color("rgba(0, 0, 0, 0.7)")
            if phase < 0:
               phase = abs(phase)
               for y in range(radius):
                   x = math.sqrt(radius**2 - y**2)
                   x = round(x)
                   X = radius - x
                   Y = radius - y
                   Y_mirror = radius + y
                   moon_width = 2 * (radius - X)
                   shade = moon_width * phase
                   shade = round(shade)
                   x_shade = X + shade
                   draw.line((X, Y), (x_shade, Y))
                   if Y_mirror != Y:
                       draw.line((X, Y_mirror), (x_shade, Y_mirror))
               draw(img)
               img.save(filename=phasepath)
            elif phase > 0:
               phase = abs(phase)
               for y in range(radius):
                   x = math.sqrt(radius**2 - y**2)
                   x = round(x)
                   X = radius + x
                   Y = radius - y
                   Y_mirror = radius + y
                   moon_width = 2 * (radius - X)
                   shade = moon_width * phase
                   shade = round(shade)
                   x_shade = X + shade
                   draw.line((X, Y), (x_shade, Y))
                   if Y_mirror != Y:
                       draw.line((X, Y_mirror), (x_shade, Y_mirror))
               draw(img)
               img.save(filename=phasepath)
    return


def printData(data):
    for i in data:
        print(i, "=", data[i])
    return




def get_phase_on_day(ddata):
    """Returns a floating-point number from 0-1. where 0=new, 0.5=full, 1=new"""
    date = ephem.Date(ddata)

    # The following extract the percent time between one new moon and the next
    # This corresponds (somewhat roughly) to the phase of the moon.
    # Note that there is a ephem.Moon().phase(), but this returns the
    # percentage of the moon which is illuminated. This is not really what we
    # want.
    nnm = ephem.next_new_moon(date)
    pnm = ephem.previous_new_moon(date)
    lunation = (date-pnm)/(nnm-pnm)
    print("lunation:" + str(lunation))
    return lunation


def main():

    dt = ephem.now().datetime()
    #dt = datetime.now()

    data = calculate(dt)
    printData(data)
    generateMoonImage(data["mp"],phasepath)
    return

if __name__=="__main__":
   main()



'''
# Write text data to text file
with open(textpath, "w") as file:
    file.write("{:.2f}\n".format(age)) #age in percent (%),new moon=0% full moon=50%
    file.write("{:.2f}\n".format(illum)) #illumination in percent (%), new moon=0% full moon=100%
    file.write("{:.0f}\n".format(dist)) #distance in Km
    file.write("{}\n".format(fullmoon)) #next full moon date and local time 
'''
