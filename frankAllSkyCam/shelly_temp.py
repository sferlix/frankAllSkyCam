'''
# read the data from the URL and print it
'''

import requests
import json

def apiCall(api_url):
    todo = {}
    r=["", ""]
    headers =  {"Content-Type":"application/json"}
    response = requests.post(api_url, data=json.dumps(todo), headers=headers)
    myjson =  response.json()
    mycode =  response.status_code
    r[0] = str(mycode)
    if mycode != "200":
       r[1] = myjson

    print(r)
    return r



def getTempHum(ip_address):
    t=["", 0, 0]
    api_url = "http://"+ip_address+"/status"
    r = apiCall(api_url)
    mycode = r[0]
    myjson = r[1]
    t[0] =  str(mycode)

    if mycode != "200":
       return

    jrelays = myjson["relays"][0]
    print(jrelays["ison"])

    jasTemp = myjson["ext_temperature"]
    if len(jasTemp)> 0:
        t[1] =  jasTemp["0"]["tC"]

    jasHum = myjson["ext_humidity"]
    if len(jasHum)> 0:
        t[2] = jasHum["0"]["tC"]

    return t



def main():
    resp = getTempHum("192.168.2.54")
    print("Temp: " + str(resp[1]))
    print("Hum : " + str(resp[2])) 

if __name__ == "__main__":
  main()

