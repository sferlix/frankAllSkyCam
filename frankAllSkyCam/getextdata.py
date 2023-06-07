'''

 read the data from the devices and return one single string
 you can lunch this file stand-alone to test if readings are ok:

 python3 getextdata.py


'''

from urllib.request import Request, urlopen
import requests
import json
from gpiozero import CPUTemperature

def getCPUTemp():
    cpu = CPUTemperature()
    return "CPU: " + str(int(cpu.temperature)) + "°C\n"

def apiCallJson(api_url):
    # generic method to call APIs returing json strings
    todo = {}
    r=["", ""]
    headers =  {"Content-Type":"application/json"}
    response = requests.post(api_url, data=json.dumps(todo), headers=headers)
    myjson =  response.json()
    mycode =  response.status_code
    r[0] = str(mycode)
    if mycode != "200":
       r[1] = myjson

    return r

def getShelly1PlusData(ip_address):
    # custom method to read info from my Shelly1 Plus (I have it inside the dome)
    t=["", 0, 0]
    temp =""
    hum=""
    DH="DH: off\n"
    api_url = "http://"+ip_address+"/status"
    r = apiCallJson(api_url)
    mycode = r[0]
    myjson = r[1]
    t[0] =  str(mycode)

    if mycode != "200":
       return

    jrelays = myjson["relays"][0]
    if jrelays["ison"]==True:
       DH ="DH: on\n"

    jasTemp = myjson["ext_temperature"]
    if len(jasTemp)> 0:
        t[1] =  jasTemp["0"]["tC"]

    jasHum = myjson["ext_humidity"]
    if len(jasHum)> 0:
        t[2] = jasHum["0"]["tC"]

    if t[1] >0:
       temp = "Int Temp: " + str(int(t[1])) + "°C\n"

    if t[2]>0:
       hum  = "Int Hum: " + str(int(t[2])) + "%\n"

    # hum sensor not installed
    return temp+hum+DH


def getMeteoStationData(target_url):
   # custom method to read info from my meteo station Davis Vantage Pro 2
   req = Request(target_url)
   req.add_header('user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36')

   lines = urlopen(req)

   counter=0
   for line in lines:
       counter +=1
       l = line.decode('utf-8')
       l = l.replace("\n", "")

       if counter  == 3:
          tempString="Temp: " +l +"°C\n"
       if counter  == 8:
          humString ="Hum: " +l +"%\n"
       if counter  == 6:
          dewString ="DewP: " +l +"°C\n"
       if counter  == 30:
          barString ="Press: " +l +" mb\n"

   # I am only interested in getting these data. So I build my string:
   myString = tempString+humString + "\n" +dewString+barString

   return myString


def getData():
    # use this method to configure your strings to be printed on the picture
    myString = getMeteoStationData("http://www.meteobrallo.com/wview/dati/realtime.txt")
    myString += getShelly1PlusData("192.168.2.54")
    myString += getCPUTemp()
    print(myString)
    return myString


def main():
    return getData()

if __name__ == "__main__":
   main()
