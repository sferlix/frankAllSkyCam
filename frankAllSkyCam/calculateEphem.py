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
print(configFileName)
appPath = os.path.expanduser("~") + "/frankAllSkyCam/"
time_zone = str(config['site']['time_zone'])
inte = str(config['site']['inte'])

logFolder = appPath + str(config['system']['logFolder'])
outputFolder = appPath + str(config['system']['otuputFolder'])

latitude  = str(config['site']['latitude'])
longitude = str(config['site']['longitude'])
elevation = int(config['site']['elevation'])

myTimeZone = str(config['site']['time_zone'])

moonpath = appPath + "/png/moon.png" #Input (full moon) image file path
phasepath = appPath+ "/png/phase.png" #Output image file path

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
   print("Input date:" + str(dt))
   tz = pytz.timezone("utc")
   mytz = pytz.timezone(myTimeZone)
   dt_utc = dt.astimezone(tz)

   #mySite
   mySite = ephem.Observer()
   mySite.lon = longitude
   mySite.lat = latitude
   mySite.elevation = elevation
   mySite.date =  dt_utc

   m=ephem.Moon()
   m.compute()
   phase = m.moon_phase
   a = m.elong
   mp = 1 - phase
   if a > 0:
       mp = -mp
   print("phase:", phase)

   sun = ephem.Sun(mySite)
   moon = ephem.Moon(mySite)

   moon_setting = ephem.localtime(mySite.next_setting(moon))
   moon_next_new = ephem.localtime(ephem.next_new_moon(mySite.date))
   moonAlt = float(moon.alt)*180/ephem.pi
   if moonAlt < 0.:
      moon_next_rising = ephem.localtime(mySite.next_rising(moon))
   else:
      moon_next_rising = ephem.localtime(mySite.previous_rising(moon))

   print("moon setting", moon_setting)

   mr = moon_next_rising.strftime("%H:%M")+  getOffset(moon_next_rising, dt)
   ms = moon_setting.strftime("%H:%M")  +getOffset(moon_setting, dt)
   nm = moon_next_new.strftime("%d %b")

   sun.compute(mySite)
   sunAlt = float(sun.alt)*180/ephem.pi

   sunSet = ephem.localtime(mySite.next_setting(sun, use_center=True))
   if sunAlt < -18.:
      sunRise = ephem.localtime(mySite.next_rising(sun, use_center=True))
      sf = "YTL"   #yes timelapse, yes startrail
   elif sunAlt >= -18. and sunAlt < 0.:
      sunRise = ephem.localtime(mySite.next_rising(sun, use_center=True))
      sf = "NTL"  #yes timelapse, no startrail
   else:
      sunRise = ephem.localtime(mySite.previous_rising(sun, use_center=True))
      sf = ""    #no timelapse, no startrail

   mySite.horizon =  '-18'  #astronomic twilight
   nightEnd = ephem.localtime(mySite.next_rising(ephem.Sun(), use_center=True))

   if sunAlt >  -18.:
      nightStart = mySite.next_setting(ephem.Sun(), use_center=True)
   else:
      nightStart = mySite.previous_setting(ephem.Sun(), use_center=True)

   nightStart = ephem.localtime(nightStart)

   sRise = sunRise.astimezone(mytz)
   sSet = sunSet.astimezone(mytz)
   nStart = nightStart.astimezone(mytz)
   nEnd = nightEnd.astimezone(mytz)

   # string management
   sr = sRise.strftime("%H:%M") + getOffset(sRise, dt)
   ss = sSet.strftime("%H:%M") + getOffset(sSet, dt)
   ns = nStart.strftime("%H:%M") + getOffset(nStart, dt)
   ne = nEnd.strftime("%H:%M") + getOffset(nEnd, dt)

   moonPhase = str(int(phase*100))+"%"

   lunation = get_phase_on_day(ephem.now().datetime())
   print("Lunation:", lunation)
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

   #Add planet info to data
   planets = calculatePlanetsVisibility(dt)
   for p in planets:
        data[p] = planets[p]

   return data

def getOffset(date1, current_date):
    getOffset = ""
    if date1.day > current_date.day:
       getOffset = "+1"
    elif date1.day < current_date.day:
       if date1.month > current_date.month:
          getOffset = "+1"
       elif date1.month == current_date.month:
          getOffset = "-1"
    else:
       getOffset=""
    #print("getOffset",getOffset)
    return getOffset

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


def calculatePlanetsVisibility(dt):
    planets_visibility = {
      "Mars": False,
      "Jupiter":False,
      "Saturn": False,
      "Venus": False
      }
 
    print("Input date:" + str(dt))
    tz = pytz.timezone("utc")
    mytz = pytz.timezone(myTimeZone)
    dt_utc = dt.astimezone(tz)

    mySite = ephem.Observer()
    mySite.lon = longitude
    mySite.lat = latitude
    mySite.elevation = elevation
    mySite.date =  dt_utc
    #mySite.horizon = '-12'
    sun = ephem.Sun(mySite)

    planets = [
     ephem.Venus(),
     ephem.Mars(),
     ephem.Jupiter(),
     ephem.Saturn()
    ]

    #sunset = mySite.previous_setting(sun)
    min_alt = 10. * math.pi / 180.
    for planet in planets:
        #mySite.date = sunset
        planet.compute(mySite)
        if planet.alt > min_alt:
           planets_visibility[planet.name] = True
    return planets_visibility

def main():
    #dt = ephem.now().datetime()
    dt = datetime.now()
    print(dt)
    data = calculate(dt)
    generateMoonImage(data["mp"],phasepath)
    planets = calculatePlanetsVisibility(dt)
    printData(data)
    return

if __name__=="__main__":
   main()



