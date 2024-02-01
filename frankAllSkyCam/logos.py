'''
this code pastes an image on the allsky image
'''

from PIL import Image
import numpy as np
import os

def imagePaste(jpg_file_name, filename, x_pos, y_pos, rot_angle):
    homePath = os.path.expanduser("~") + "/frankAllSkyCam/"
    c_filename = homePath + filename
    if c_filename != "":
       if os.path.isfile(c_filename):
          cmp = Image.open(c_filename)
          if rot_angle > 0:
             comp = cmp.rotate(rot_angle)
          else:
             comp = cmp
       else:
          print("File " + c_filename + " not existing")

    background = Image.open(jpg_file_name)
    background.paste(comp, (x_pos,y_pos), comp.convert('RGBA') )
    background.save(jpg_file_name,"jpeg")
    return


def imagesPaste(images, jpg_file_name):
    homePath = os.path.expanduser("~") + "/frankAllSkyCam/"
    background = Image.open(jpg_file_name)

    for i in images:
      printItem=images[i][0]
      filename =images[i][1]
      x_pos =images[i][2]
      y_pos = images[i][3]
      rot_angle = images[i][4]
      print(i, printItem,filename,x_pos,y_pos, rot_angle)
      c_filename = homePath + "png/" + filename
      if printItem==True:
         if os.path.isfile(c_filename):
            cmp = Image.open(c_filename)
            if rot_angle > 0:
               comp = cmp.rotate(rot_angle)
            else:
               comp = cmp
            background.paste(comp, (x_pos,y_pos), comp.convert('RGBA'))
         else:
            print("File " + c_filename + " not existing")
      else:
         print("File " + c_filename + " not needed")

    print("saving file...")
    background.save(jpg_file_name,"jpeg")
    return


def main():
    # this main operates only for testing purposes.
    homePath = os.path.expanduser("~") + "/frankAllSkyCam/"
    jpg_filename = homePath +  "skycam.jpg"

    imagePaste(jpg_filename, "compass.png",900,580,20)
    imagePaste(jpg_filename, "logo.png",30,580,0)
    imagePaste(jpg_filename, "phase.png",900,300,0)
    return

if __name__ == "__main__":
  main()
