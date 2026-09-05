'''

 read the data from your text file and return one single string
 you can lunch this file stand-alone to test if readings are ok:

 python3 getextdata.py


'''

import os

def getData(fileName):
    # use this method to configure your strings to be printed on the picture
    myString = getDataFromTxtFile(fileName)

    #if you wish to add Pi CPU Temp, uncomment the import and getCPUTemp()
    #call below (kept out by default: extra_data.txt already includes CPU
    #temp from the external sensor script, and gpiozero adds GPIO backend
    #init overhead to every capture when unused)
    #from gpiozero import CPUTemperature
    #myString += getCPUTemp()

    print(myString)
    return myString


def getCPUTemp():
    from gpiozero import CPUTemperature
    cpu = CPUTemperature()
    return "CPU: " + str(int(cpu.temperature)) + "°C\n"


def getDataFromTxtFile(fileName):
    myString = ""
    if fileName != "":
       if os.path.isfile(fileName):
          with open(fileName, encoding='utf8') as f:
               myString = f.read()

    return myString

def main():
    return getData("test.txt")

if __name__ == "__main__":
   main()
