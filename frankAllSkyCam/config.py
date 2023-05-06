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
# 
# directory where to save logs
logFolder = log

# directory  where to save SQM LE readings
sqmFolder = sqm

# web folder where to save the skycam.jpg
outputLocalWebFile = /var/www/html/img/skycam.jpg

#how many days you want to keep jpgs
days_retention = 3

#watchdog will reboot if after x minutes no image has been generated 
rebootAfter = 5

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
additional_params = "--gain 18 --awbgains 2.2,2.2"


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


[exposure]
#night exposure in seconds
# urban sky:
#esp_secs = 4
# dark sky (i found 55 secs ok for sqm 21,3).
# adjust according to your sky
esp_secs =60
# max exposure during dawn and dusk:
esp_dawn_dusk = 40 

[moon]
#exposure reduction because of the moon
full_moon_reduc = 0.75

# minutes after moonset
ms_offset = -30

# minutes from moonset-start to no-moon
ms_duration = 50      

# minutes *before* the moon rises
mr_offset = -30 

# minutes from moon-rise to moon fully up
mr_duration = 60


[offset]
# minutes to offset dawn and dusk for optimal exposure 
dawn = 0
dusk = 0

[ftp]
# if True, allSkyCam image, timelapse and startrails 
#will be uploaded on your FTP Server 
isFTP=True

# ftp parameters allSkyCam image will be uploaded on a 
FTP_server=yourftp.com
FTP_login=yourlogin
FTP_pass=yourpass
FTP_uploadFolder =/public_html/webcam/allsky

# allskycam.jpg will be generated on the FTP server
FTP_filenameAllSkyImgJPG = allskycam 

# allskycam_night.mp4 will be generated if nightTL = True
# allskycam_24h.mp4 will be generated if fullTL = True
FTP_fileNameTimelapseMP4 = /videos/frankAllSkycam

# starTrail.jpg will be generated 
FTP_fileNameStarTrailJPG = /startrails/starTrail.jpg

[sqm_le]
# if you want to use SQM LE then use_sqm = y Otherwise, not.
use_sqm = n
ip_address = 192.168.1.100
port = 10001
write_log = n

