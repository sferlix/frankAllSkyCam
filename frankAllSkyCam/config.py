########################################
# frankAllSkyCam
# configuration file -  config.txt
#
# please adjust according to your needs
# see comments and documentation
########################################

[system]
# where will be stored images - relative path to frankAllSkyCam
otuputFolder= img

# directory where to save logs
logFolder = log

# local web folder where to save the skycam.jpg
outputLocalWebFile = /var/www/html/img/skycam.jpg

#how many days you want to keep jpgs
days_retention = 3

#watchdog will reboot if after x minutes no image has been generated
rebootAfter = 15

[site]
#the following label will be printed on the image
inte = www.astrobrallo.com
latitude = 44.73
longitude = 9.31
time_zone = Europe/Rome

[resolution]
# may use  1024 x 768
horiz = 800
vert = 600
picture_rotation = 0

[libcamera]
# may personalize the libcamara params.
# please DO NOT set --shutter, --immediate
# parameters will be used only when exposure > 0
additional_params = --gain 14 --awbgains 2.2,1.6 --contrast 1.5


[timelapse]
# if True, timelapse from sunset to sunrise will be generated  Otherwise, not.
nightTL = True

# if True, 24h timelapse from 9am to 9am next day will be generated. Otherwise, not.
fullTL = True
nightOnly = True

# following parameters are used by ffmpeg
tl_horiz = 800
tl_vert = 600
framerate = 10
ffmpeg1 = -c:v libx264 -crf 12 -preset slow -pix_fmt yuv420p
# additional ffmpeg parameters may be added by experts!
ffmpeg2 =
ffmpeg3 =

[font]
#when 1024x768 you can increase it
font_size = 18
font_colorR = 0
font_colorG = 255
font_colorB = 255

[extra_text]
et_use= n
et_font_size = 18
et_font_colorR = 0
et_font_colorG = 255
et_font_colorB = 255
et_x_pos = 5
et_y_pos = 80


[exposure]
# max night exposure in seconds
#  for urban sky, suggested value is 4
#  for dark sky, suggested value is 55-60 (I found 55 secs ok for sqm 21,3).
#  this value only limits the max exposure. The calculated or real SQM will drive exposure
esp_secs =60

[offset]
# minutes to offset dawn and dusk for optimal exposure
dawn = 0
dusk = 0

[ftp]
# if True, allSkyCam image, timelapse and startrails
#will be uploaded on your FTP Server
isFTP=False

# ftp parameters, to upload the allSkyCam image to your FTP server
FTP_server=yourftpserver.com
FTP_login=username
FTP_pass=password
FTP_uploadFolder =/public_html

# uploaded file name (e.g.,allskycam.jpg)
FTP_filenameAllSkyImgJPG = img/allskycam

# allskycam_night.mp4 will be generated if nightTL = True
# allskycam_24h.mp4 will be generated if fullTL = True
FTP_fileNameTimelapseMP4 = /video/frankAllSkycam

# starTrail.jpg will be generated
FTP_fileNameStarTrailJPG = /startrail/startrail.jpg

[sqm]
# directory where to save sqm info
sqmFolder = sqm
# would you use the SQM-LE ? y/n
use_sqm_le = n
# would you log your SQM ? y/n
sqmLog = n
# keep sqmDebug = n
sqmDebug = n
# in case you have SQM-LE, put your IP/port
ip_address = 192.168.2.59
port = 10001

