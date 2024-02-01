'''

 read the data from your text file and return one single string
 you can lunch this file stand-alone to test if readings are ok:

 python3 getextdata.py


'''

from gpiozero import CPUTemperature
import os

def getData(fileName):
    # use this method to configure your strings to be printed on the picture
    myString = getDataFromTxtFile(fileName)

    #uncomment the following line if you wish to add Pi CPU Temp:
    #myString += getCPUTemp()

    print(myString)
    return myString


def getCPUTemp():
    cpu = CPUTemperature()
    return "CPU: " + str(int(cpu.temperature)) + "°C\n"


def getDataFromTxtFile(fileName):
    myString = ""
    if fileName != "":
       if os.path.isfile(fileName):
          with open(fileName, encoding='utf8') as f:
               myString = f.read()
               f.close()

    return myString

def main():
    return getData("test.txt")

if __name__ == "__main__":
   main()
