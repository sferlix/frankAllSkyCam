from PIL import Image
import numpy as np
import os

def main():
    imagePaste("compass.png", 900,580,20, "logo.png", 30, 580)
    return



def imagePaste(jpg_file_name, compass_filename, compass_x_pos, compass_y_pos, compass_rot_angle, logo_filename, logo_x_pos, logo_y_pos):
    print(compass_filename)
    homePath = os.path.expanduser("~") + "/frankAllSkyCam/"
    compass_filename = homePath + compass_filename
    logo_filename = homePath + logo_filename
    print(compass_filename)

    paste_comp = False
    paste_logo = False
    if compass_filename != "":
       if os.path.isfile(compass_filename):
          cmp = Image.open(compass_filename)
          comp = cmp.rotate(compass_rot_angle)
          paste_comp = True

    if logo_filename != "":
       if os.path.isfile(logo_filename):
          logo = Image.open(logo_filename)
          paste_logo = True

    if paste_comp==True or paste_logo == True:
       background = Image.open(jpg_file_name)
       if paste_comp ==  True:
          background.paste(comp, (compass_x_pos, compass_y_pos),comp.convert('RGBA') )

       if paste_logo == True:
          background.paste(logo, (logo_x_pos, logo_y_pos),logo.convert('RGBA') )

       background.save(jpg_file_name,"jpeg")

    return




if __name__ == "__main__":
  main()
