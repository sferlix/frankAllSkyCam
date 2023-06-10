# frankAllSkyCam - AllSkyCam software 

Here is what you need to install, after ensuring to satisfy requirements (see below):

# pip3 install frankAllSkyCam

installation is done.
Launch the program:

python3 -m frankAllSkyCam

to configure your system, edit the single config.txt like this:

nano /home/pi/frankAllSkyCam/config.txt

details below. Enjoy !



# 1. PREREQUISITES
prepare a clean SD card with the last version of raspbian. Lite version, without desktop is fine. 
The important point is that your OS must have the libcamera software (included in the last Raspberry OS).
The former version (raspistill) is not supported.If you want to check if you have libcamera installed, just type this command:

libcamera-jpeg -o test.jpg --immediate -n

you should find test.jpg in your current folder

Supposing you are fine with this pre-requisite, let's start

# 2. Ensure everything is updated:

sudo apt update

sudo apt upgrade

# 3. install the software eventually needed:

a) Apache (web server). it is not really mandatory. If your Raspberry will not be also used as web server, skip this point.


If you want to use your Raspberry Pi as web server, then install Apache:

sudo apt install apache2 -y

b) Install pip (should be already in you raspberry)

sudo apt install python3-pip


done !

Now you can install frankAllSkyCam


pip3 install frankAllSkyCam

before configuring, please note that,
if you are going to use your Raspberry as a web server, to present your allSky images, after the installation, you need to create the images folder in your web server. I also provide you a very basic html page to show the allSky image.

To do so, type these 2 commands:

sudo mkdir /var/www/html/img

sudo mv /home/pi/frankAllSkyCam/index.html /var/www/html/



# 4. configure your system


to configure your system, edit the single config.txt file:

/home/pi/frankAllSkyCam/config.txt

To edit the config.txt, you could use the nano editor:

nano config.txt

I would suggest to update at minimum the following parameters:
inte = <name of your AllSkyCam that will be printed on top-center of the allSky images>
latitude = 44.73
longitude = 9.31
time_zone = Europe/Rome

in case you own the SQM-LE, turn the use_sqm =n in y and put the IP address and port of the SQM-LE.
  
use_sqm = y
  
ip_address = <ip_address_of_the_SQM_LE>
  
port = 10001
  
write_log = n
  

in case you publish the allskycam, startrail images and timelapses videos in a remote website, you can do it by using an FTP transfer. If this is the case, configure the parameters as explained below.
  
parameters to configureFTP_server = <your_ftpserver.com>
FTP_login = your_user
  
FTP_pass = your_password
  
FTP_uploadFolder =your_upload_dir
  
FTP_filenameAllSkyImgJPG = allskycam
  
FTP_fileNameStarTrailJPG = /startrails/starTrail.jpg
  
FTP_fileNameTimelapseMP4 = /videos/frankAllSkycam
 

allskycam_night.mp4 will be generated if nightTL = True
 
allskycam_24h.mp4 will be generated if fullTL = True

if you do not want to use a remote FTP just set this way:
  
isFTP=False
  
There are many other options. The config.txt file is self-explanatory and you can customize many things, including logo, compass, extra-data you may want to print on your AllSkyCam image
  

 # 5. Test to check if it works:

from command line, just type:

python3 -m frankAllSkyCam

if it works, you should find the generated JPGs:

1. via browser, test http://<your_raspberry_IP>
2. /home/pi/frankAllSkyCam/img/<img_folder_with_date>/<jpg files>
3. on your remote FTP, in case you have configured it
  

==============================
  
# 6. Last step. 
  
If everything works, just make everything automatic. 
Type this command:

python3 -m frankAllSkyCam.crontab
  
it will install all the jobs
  
==============================
 
  
# For expert users 
   
  /home/pi/frankAllSkyCam/sqmexp.csv
  
  (e.g., nano   /home/pi/frankAllSkyCam/sqmexp.csv)

 you just need to change the exposure for every given SQM value. If you wish, you can also add more pairs (sqm values, secs).
 The software would predict the exposure duration by interpolating among existing values (polynomial regression grade=3).
 You may want calibrate your exposures and combine it with your desired --gain and --awbgains options (in config.txt)  
 In any case, the max exposure value will not exceed the esp_secs parameter in config.txt
  
 ================================== 
Done !
enjoy it !
