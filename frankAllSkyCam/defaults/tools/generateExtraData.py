'''
 read the data from your devices/sensors and return one single string
 to be watermarked on the AllSkyCam image (see extra_data.txt / config.txt
 [extra_text] section).

 *** THIS FILE IS MEANT TO BE EDITED BY YOU ***
 It lives in ~/frankAllSkyCam/tools/, outside the installed frankAllSkyCam
 package, specifically so that upgrading the package (pip install --upgrade)
 never overwrites your customizations. Add your own sensors/devices to
 getData() below.

 Your device/credentials go in generateExtraData.conf, sitting next to this
 file (NOT the main frankAllSkyCam config.txt - this one is independent, on
 purpose, so this script can be handed to/edited by an end user without
 needing to touch the core package config).

 You can launch this file stand-alone to test if readings are ok:
 python3 generateExtraData.py
'''

import os
import json
import time
import urllib.request
from configparser import ConfigParser
from ftplib import FTP

basePath = os.path.expanduser("~") + "/frankAllSkyCam/"
scriptDir = os.path.dirname(os.path.realpath(__file__))
configFileName = scriptDir + "/generateExtraData.conf"

config = ConfigParser()
if config.read(configFileName):
    METEO_ENABLED = str(config['meteo']['enabled']) == 'True'
    METEO_STATION_URL = config['meteo']['station_url']
    WS90FTP_ENABLED = str(config['ftp']['enabled']) == 'True'
    FTP_HOST = config['ftp']['host']
    FTP_USER = config['ftp']['user']
    FTP_PASS = config['ftp']['pass']
    FTP_UPLOAD_PATH = config['ftp']['upload_path']

    DEW_HEATER_ENABLED = str(config['dew_heater']['enabled']) == 'True'
    DEW_HEATER_METHOD = config['dew_heater']['method']
    DEW_HEATER_MARGIN_C = float(config['dew_heater']['margin_c'])
    DEW_HEATER_SHELLY_IP = config['dew_heater']['shelly_ip']
    DEW_HEATER_GPIO_PIN = int(config['dew_heater']['gpio_pin'])
    DEW_HEATER_GPIO_ACTIVE_LOW = str(config['dew_heater']['gpio_active_low']) == 'True'
else:
    print("WARNING: " + configFileName + " not found - edit it and re-run. "
          "Falling back to empty settings for now.")
    METEO_ENABLED = False
    METEO_STATION_URL = ""
    WS90FTP_ENABLED = False
    FTP_HOST = ""
    FTP_USER = ""
    FTP_PASS = ""
    FTP_UPLOAD_PATH = ""

    DEW_HEATER_ENABLED = False
    DEW_HEATER_METHOD = "shelly"
    DEW_HEATER_MARGIN_C = 10.0
    DEW_HEATER_SHELLY_IP = ""
    DEW_HEATER_GPIO_PIN = 17
    DEW_HEATER_GPIO_ACTIVE_LOW = False


def sendWS90_data_to_web(json_path):
    print("send WS90 data to Web")
    try:
        ftp = FTP(FTP_HOST, FTP_USER, FTP_PASS)
        with open(json_path, "rb") as f:
            ftp.storbinary("STOR " + FTP_UPLOAD_PATH, f)
        ftp.quit()
        print("FTP OK")
    except Exception as e:
        # best-effort: a failed upload must never take down the caller,
        # which already has the sensor string it needs by this point
        print("FTP ERROR: " + str(e))


def getInternalTempHum():
    # lettura temperatura ed umidita' (SHT31-like I2C sensor)
    import smbus
    i2c = smbus.SMBus(1)
    addr = 0x44
    i2c.write_byte_data(addr, 0x23, 0x34)
    time.sleep(0.5)
    i2c.write_byte_data(addr, 0xe0, 0x0)
    data = i2c.read_i2c_block_data(addr, 0x0, 6)
    rawT = ((data[0]) << 8) | (data[1])
    rawR = ((data[3]) << 8) | (data[4])
    T = round(-45 + rawT * 175 / 65535, 1)
    RH = round(100 * rawR / 65535)
    return T, RH


def getCPUTemp():
    from gpiozero import CPUTemperature
    cpu = CPUTemperature()
    return "CPU: " + str(int(cpu.temperature)) + "°C\n"


import requests
from requests.exceptions import RequestException, HTTPError, ConnectionError, Timeout


def apiCallJson(url, max_retries=3, backoff_factor=2):
    """
    Interroga un'API JSON con gestione dei retry e backoff esponenziale.

    :param url: L'indirizzo dell'API da interrogare.
    :param max_retries: Numero massimo di tentativi in caso di errore di rete.
    :param backoff_factor: Moltiplicatore per l'attesa tra i tentativi.
    :return: Dizionario JSON in caso di successo, "" altrimenti.
    """
    headers = {'Connection': 'close', 'Accept': 'application/json'}

    for attempt in range(max_retries):
        try:
            print(f"Tentativo {attempt + 1} di {max_retries}...")
            response = requests.get(url, headers=headers, timeout=10)
            return response.json()

        except HTTPError as http_err:
            print(f"Errore HTTP: {http_err}")
            if 400 <= response.status_code < 500:
                break
        except (ConnectionError, Timeout) as conn_err:
            print(f"Errore di rete: {conn_err}")
        except RequestException as req_err:
            print(f"Errore generico durante la richiesta: {req_err}")

        if attempt < max_retries - 1:
            wait_time = backoff_factor ** (attempt + 1)
            print(f"Attesa di {wait_time} secondi prima del prossimo tentativo...")
            time.sleep(wait_time)

    print("Impossibile recuperare i dati dopo i tentativi massimi.")
    return ""


def getShelly1PlusHT(ip_address):
    # custom method to read info from a Shelly1 Plus (e.g. inside the dome)
    api_url = "http://" + ip_address + "/rpc/Shelly.GetStatus"
    myjson = apiCallJson(api_url)
    if not myjson:
        return "", ""
    H = myjson.get('humidity:100', {}).get('rh')
    T = myjson.get('temperature:100', {}).get('tC')
    return T, H


def getShellyUniPlusXvoltage(ip_address):
    # custom method to read info from a Shelly Uni Plus (e.g. voltage sensor)
    api_url = "http://" + ip_address + "/rpc/Shelly.GetStatus"
    myjson = apiCallJson(api_url)
    if not myjson:
        return ""
    jasVolt = myjson.get("voltmeter:100", {})
    volt = str(jasVolt["xvoltage"]) if jasVolt else ""
    return volt


def getShelly1V3Data(ip_address):
    # custom method to read info from a Shelly1 V3 (with ext temp sensor)
    api_url = "http://" + ip_address + "/status"
    myjson = apiCallJson(api_url)
    if not myjson:
        return ""
    jasTemp = myjson.get("ext_temperature", {})
    if not jasTemp:
        return ""
    t1 = jasTemp["0"]["tC"]
    return str(round(t1, 1))


def getShelly1V3SwitchStatus(ip_address):
    # custom method to read the relay status from a Shelly1 V3
    api_url = "http://" + ip_address + "/status"
    myjson = apiCallJson(api_url)
    if not myjson:
        return "??"
    isOn = myjson["relays"][0]["ison"]
    return "On" if isOn else "Off"


def gradi_in_direzione(gradi):
    """Converte un valore in gradi (0-360) nella relativa direzione cardinale/intercardinale."""
    direzioni = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
    idx = int((gradi + 22.5) % 360 // 45)
    return direzioni[idx]


WS90_NAME_MAP = {
    "wind_speed": "Wind",
    "pressure_msl": "Press",
    "temperature_s": "Temp",
    "dewpoint": "Dew P",
    "humidity_u8": "Hum",
    "humidity": "H"
}

WS90_ORDER = ["wind_speed", "pressure_msl", "temperature_s", "dewpoint", "humidity_u8"]


def _formatWS90Sensors(sensors):
    # parses the "sensors" dict from a WS90-style JSON payload into the
    # display string
    stringa_finale = ""
    for key in WS90_ORDER:
        sensor_key = key
        if sensor_key not in sensors and sensor_key == "humidity_u8" and "humidity" in sensors:
            sensor_key = "humidity"

        if sensor_key in sensors:
            descrizione = WS90_NAME_MAP.get(sensor_key, sensor_key)
            valore = sensors[sensor_key]["value"]
            unita = sensors[sensor_key]["unit"]

            if unita == "C":
                unita = "°C"

            if sensor_key == "wind_speed":
                dir_str = ""
                if "wind_direction" in sensors and isinstance(sensors["wind_direction"]["value"], (int, float)):
                    dir_val = gradi_in_direzione(sensors["wind_direction"]["value"])
                    dir_str = f" {dir_val}"
                linea = f"{descrizione}: {valore} {unita}{dir_str}".strip() + "\n"
            else:
                linea = f"{descrizione}: {valore} {unita}".strip() + "\n"

            stringa_finale += linea

    return stringa_finale


def getMeteoStationData(api_url):
    # custom method to read info from an Ecowitt WS90-style weather station,
    # given its full JSON URL (local device or a published feed).
    # returns (display_string, sensors_dict) - sensors_dict lets callers
    # (e.g. checkAndSwitchDewHeater) reuse a raw reading like "dewpoint"
    # without a second network round-trip.
    if not METEO_ENABLED:
        return "", {}

    print(api_url)
    json_path = basePath + "tools/ws90_data.json"

    stringa_finale = ""
    sensors = {}
    try:
        # some hosts (e.g. a shared-hosting WAF in front of a published feed)
        # reject urllib's default/short UA strings with a 406 - a full
        # browser-style one works reliably against both a local device and
        # a web-published feed
        req = urllib.request.Request(api_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        with urllib.request.urlopen(req, timeout=10) as response:
            json_data_bytes = response.read()
            json_str = json_data_bytes.decode('utf-8')

        data = json.loads(json_str)
        json.dump(data, open(json_path, "w"), indent=2)

        sensors = data.get("sensors", {})
        stringa_finale = _formatWS90Sensors(sensors)
    except Exception as e:
        print(f"Errore durante il recupero o l'elaborazione dei dati: {e}")
        return stringa_finale, sensors

    # non-critical: upload the raw json to the website, only after the
    # watermark string above is already built, so an upload failure can
    # never discard a successful sensor reading. Opt-in via config.
    if WS90FTP_ENABLED:
        sendWS90_data_to_web(json_path)

    print(stringa_finale)
    return stringa_finale, sensors


def getDavisVantageProData(target_url):
    # custom method to read dew point + pressure from a Davis Vantage Pro2
    # weather station's plaintext realtime.txt report.
    # returns (display_string, {"dewpoint": float_or_None, "pressure": float_or_None})
    if not METEO_ENABLED:
        return "", {"dewpoint": None, "pressure": None}

    try:
        req = urllib.request.Request(target_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

        dewString = ""
        barString = ""
        dewPoint = None
        pressure = None
        counter = 0
        with urllib.request.urlopen(req, timeout=10) as lines:
            for line in lines:
                counter += 1
                l = line.decode('utf-8').replace("\n", "")

                if counter == 13:
                    dewString = "DewP: " + l + "°C\n"
                    try:
                        dewPoint = float(l)
                    except ValueError:
                        pass
                if counter == 30:
                    barString = "Press: " + l + " mb\n"
                    try:
                        pressure = float(l)
                    except ValueError:
                        pass

        stringa_finale = dewString + barString
        print(stringa_finale)
        return stringa_finale, {"dewpoint": dewPoint, "pressure": pressure}
    except Exception as e:
        print("getDavisVantageProData error: " + str(e))
        return "", {"dewpoint": None, "pressure": None}


def getDataFromTxtFile(fileName):
    myString = ""
    if fileName != "":
        if os.path.isfile(fileName):
            with open(fileName, encoding='utf8') as f:
                myString = f.read()
    return myString


def writeDataToTxtFile(myString, myFile):
    # write-then-rename so a concurrent reader (getextdata.py, during a
    # capture) never sees a half-written file
    tmpFile = myFile + ".tmp"
    with open(tmpFile, 'w') as f:
        f.write(myString)
    os.replace(tmpFile, myFile)


def getDHStatus2(pin):
    import RPi.GPIO as GPIO
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.IN)
    state = GPIO.input(pin)
    return 'DH: on\n' if state else 'DH: off\n'


def _dewHeaterApiCall(api_url):
    # POST-based call used specifically for switching a Shelly relay
    # (distinct from apiCallJson: no retries - a relay command shouldn't be
    # silently retried several seconds late)
    try:
        headers = {"Content-Type": "application/json"}
        response = requests.post(api_url, data="{}", headers=headers, timeout=10)
        return str(response.status_code), response.json()
    except Exception as e:
        print("dew heater apiCall error: " + str(e))
        return "", None


def switchShellyRelay(ip_address, comando):
    if comando != "on" and comando != "off":
        return None
    api_url = "http://" + ip_address + "/relay/0?turn=" + comando
    mycode, myjson = _dewHeaterApiCall(api_url)
    return [mycode, myjson]


def switchGpioRelay(pin, comando, active_low=False):
    import RPi.GPIO as GPIO
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.OUT)
    on_level = GPIO.LOW if active_low else GPIO.HIGH
    off_level = GPIO.HIGH if active_low else GPIO.LOW
    GPIO.output(pin, on_level if comando == "on" else off_level)


def checkAndSwitchDewHeater(intTemp, dewPoint):
    # switches the dew heater on/off based on (intTemp - dewPoint), reusing
    # values getData() already fetched for the watermark text. Never raises:
    # a heater-control failure must not prevent extra_data.txt from being
    # written.
    if not DEW_HEATER_ENABLED:
        return
    if intTemp is None or dewPoint is None:
        print("Dew heater check skipped: missing temp/dewpoint reading.")
        return

    try:
        delta = float(intTemp) - float(dewPoint)
        comando = "on" if delta < DEW_HEATER_MARGIN_C else "off"
        print("Dew heater check: intTemp=" + str(intTemp) + "°C, dewPoint=" + str(dewPoint) +
              "°C, delta=" + str(round(delta, 1)) + "°C -> " + comando)

        if DEW_HEATER_METHOD == "shelly":
            resp = switchShellyRelay(DEW_HEATER_SHELLY_IP, comando)
            if resp is None or resp[0] != "200":
                print("error while switching dew heater relay (shelly)!")
                return
            print("Dew heater switched " + comando + " (shelly)")
        elif DEW_HEATER_METHOD == "gpio":
            switchGpioRelay(DEW_HEATER_GPIO_PIN, comando, DEW_HEATER_GPIO_ACTIVE_LOW)
            print("Dew heater switched " + comando + " (gpio pin " + str(DEW_HEATER_GPIO_PIN) + ")")
        else:
            print("Unknown dew_heater method in config: " + DEW_HEATER_METHOD)
    except Exception as e:
        print("Dew heater check/switch error: " + str(e))


def getData():
    # use this method to configure your strings to be printed on the picture.
    # every sensor call below is independent and optional: commenting one
    # out (e.g. if you don't have a weather station) just omits it - it
    # cannot crash this function, since every variable it could touch is
    # given a safe default up front.
    MeteoS, meteoSensors = "", {}
    T, H = "", ""
    Ta = ""
    isOn = ""
    intT, intH = "", ""
    dhStatus = ""

    # weather station - pick ONE (or comment both out if you don't have one):
    print("collecting data from Meteo Station ...")
    # MeteoS, meteoSensors = getMeteoStationData(METEO_STATION_URL)   # WS90/Ecowitt (JSON)
    # MeteoS, meteoSensors = getDavisVantageProData("http://www.example.com/wview/dati/realtime.txt")  # Davis Vantage Pro2 (plaintext)
    print(MeteoS)


    print("collecting wind from 192.168.178.25...")
    myWind = "Wind:" +  getShellyUniPlusXvoltage('192.168.178.25') + " Km/h\n"
    print(myWind)
    

    # other sensor examples (uncomment and configure as needed):
    T, H = getShelly1PlusHT("192.168.178.147")
    Ta = getShelly1V3Data("192.168.178.8")
    # isOn = getShelly1V3SwitchStatus("192.168.1.54")
    intT, intH = getInternalTempHum()
    dhStatus = getDHStatus2(17)

    myString = ""
    myString += MeteoS
    myString += getCPUTemp()

    # dew heater: reuses whichever temp/dewpoint values are already
    # available above - wire in whatever this installation actually has.
    # e.g. with the WS90 station and a Shelly1V3 providing internal temp:
    # dewPoint = meteoSensors.get("dewpoint", {}).get("value")
    dewPoint = None
    intTemp = float(Ta) if Ta else None
    checkAndSwitchDewHeater(intTemp, dewPoint)

    print("########################")
    print("String to be displayed:")
    print("########################")
    print(myString)
    return myString


def main():
    myFile = basePath + "extra_data.txt"
    myString = getData()
    writeDataToTxtFile(myString, myFile)
    return


if __name__ == "__main__":
    main()
