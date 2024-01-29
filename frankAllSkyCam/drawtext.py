'''
to print info on the AllSkyCam jpg file
'''

from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw


def printWatermark(s, nomefile, font_size, fc, sqm_le, rotation, text_positions, extra_text):
    data      = s["data"]
    ora       = s["ora"]
    inte      = s["inte"]
    TL        = s["suffisso"]
    moon_rise = s["moonRise"]
    moon_set  = s["moonSet"]
    srise     = s["sunRise"]
    sset      = s["sunSet"]
    NS        = s["nightStart"]
    NE        = s["nightEnd"]
    phase     = s["moonPhase"]
    fract     = ""
    esposiz   = s["exposure"]
    sqm       = s["sqm"]
    newMoon   = s["newMoon"]
   
    photo = Image.open(nomefile)
    if rotation!=0:
       new_photo=photo.rotate(rotation)
       new_photo.save(nomefile)
       photo = Image.open(nomefile)

    drawing = ImageDraw.Draw(photo)
    font = ImageFont.truetype("DejaVuSerif.ttf", font_size)
    if len(fc)==0:
       fc=[255,0,0]

    if sqm > 18:
       fc=[247,13,26]

    colore = (fc[0], fc[1],fc[2])

    pos=(text_positions[0][0], text_positions[0][1])
    stringa = data + " - " + ora
    if esposiz>0:
       esposiz = esposiz 
       stringa = stringa + "\nExp(s) = " + str(round(esposiz,2))

    drawing.text(pos, stringa, fill=colore, font=font)

    pos=(text_positions[4][0], text_positions[4][1])
    stringa = inte
    drawing.text(pos, stringa, fill=colore, font=font)

    pos=(text_positions[3][0], text_positions[3][1])
    stringa = "Sunrise " + srise + "\nSunset " + sset
    drawing.text(pos, stringa, fill=colore, font=font)

    pos=(text_positions[2][0], text_positions[2][1])

    stringa_sqm = "\ncSQM: "
    if sqm_le == 'y':
       stringa_sqm = "\nSQM: "

    stringa = "Night Start "+ NS +"\nNight End "+ NE + stringa_sqm + str(round(sqm,2))
    drawing.text(pos, stringa, fill=colore, font=font)

    pos=(text_positions[1][0], text_positions[1][1])
    stringa = "Moonrise " + moon_rise + "\nMoonset " + moon_set + "\n" + str(fract) + phase+"\nNew Moon: " + newMoon 
    drawing.text(pos, stringa, fill=colore, font=font)

    if len(extra_text) > 1:

       et_pos=(extra_text[3],extra_text[4])
       et_stringa = extra_text[0]

       et_colore =(extra_text[2][0],extra_text[2][1],extra_text[2][2])

       if sqm>18:
          et_colore = colore

       et_font = ImageFont.truetype("DejaVuSerif.ttf", extra_text[1])
       drawing.text(et_pos, et_stringa, fill=et_colore, font=et_font)



    photo.save(nomefile)
    return


