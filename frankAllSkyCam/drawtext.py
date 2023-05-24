# import all the libraries
from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw


def printWatermark(s, nomefile, font_size, fc, sqm_le):
    data      = s[0]
    ora       = s[1]
    inte      = s[2]
    TL        = s[4]
    moon_rise = s[5]
    moon_set  = s[6]
    srise     = s[7]
    sset      = s[8]
    NS        = s[9]
    NE        = s[10]
    phase     = s[11]
    fract     = s[12]
    esposiz   = s[13]
    sqm       = s[14]

    photo = Image.open(nomefile)
    drawing = ImageDraw.Draw(photo)
    font = ImageFont.truetype("DejaVuSerif.ttf", font_size)
    if len(fc)==0:
       fc=[255,0,0]

    if sqm > 18:
       fc=[247,13,26]

    colore = (fc[0], fc[1],fc[2])

    pos=(5, 0)
    stringa = data + "\n" + ora
    if esposiz>0:
       esposiz = round(esposiz / 1000000,3)
       stringa = stringa + "\nExp(s) = " + str(esposiz)

    drawing.text(pos, stringa, fill=colore, font=font)

    pos=(300, 0)
    stringa = inte
    drawing.text(pos, stringa, fill=colore, font=font)

    pos=(670,0)
    stringa = "Sunrise " + srise + "\nSunset " + sset 
    drawing.text(pos, stringa, fill=colore, font=font)

    pos=(5, 535)
    stringa_sqm = "\ncSQM: "
    if sqm_le == 'y':
       stringa_sqm = "\nSQM: "

    stringa = "Night Start "+ NS +"\nNight End "+ NE + stringa_sqm + str(round(sqm,2))
    drawing.text(pos, stringa, fill=colore, font=font)

    pos=(630,535)
    stringa = "Moonrise " + moon_rise + "\nMoonset " + moon_set + "\n" + str(fract) + "% | " + phase
    drawing.text(pos, stringa, fill=colore, font=font)

    photo.save(nomefile)
    return
