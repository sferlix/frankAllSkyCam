# frankAllSkyCam - AllSkyCam software 

Here is what you need to install

# pip3 install frankAllSkyCam

installation is done.
Launch the program:

python3 -m frankAllSkyCam

to configure your system, edit the single config.txt like this:

nano /home/pi/frankAllSkyCam/config.txt

details below. Enjoy !



# 1. PREREQUISITES
(not really mandatory) prepare a clean SD with the last version of raspbian. Lite version, without desktop is fine. 
The important point is that your OS should have libcamera software (included in the last Raspberry OS).
The former version (raspistill) is not supported.If you want to check if you have libcamera installed, just type this command:

libcamera-jpeg -o test.jpg --immediate -n

you should find test.jpg in your current folder

Supposing you are fine with this pre-requisite, let's start

# 2. Ensure everything is updated:

sudo apt update

sudo apt upgrade

# 3. install the software needed:

a) Apache (web server). it is not really mandatory. If you would skip this, change the parameter in the config.txt (see below)

outputLocalWebFile = /home/pi/frankAllSkyCam/img/skycam.jpg

if you want to use your Raspberry Pi as web server, then install Apache:

sudo apt install apache2 -y

b) Install pip (should be already in you raspberry)

sudo apt install python3-pip


if you are going to use your Raspberry as a web server to present your allSky images, after the installation, you need to create the images folder in your web server. I also provide you a very basic html page to show the all sky image.

To do so, type these 2 commands:

sudo mkdir /var/www/html/img

sudo mv /home/pi/frankAllSkyCam/index.html /var/www/html/



# 4. configure your system


to configure your system, edit the single config.txt file:

/home/pi/frankAllSkyCam/config.txt

To edit the config.txt, you could use the nano editor:

nano config.txt

I would suggest to update at minimum the following parameters:
inte = <name of your AllSkyCam that will be on top-center of the allSky image>
latitude = 44.73
longitude = 9.31
time_zone = Europe/Rome

in case you own the SQM-LE, turn the use_sqm =n in 'y' and put the IP address of the SQM-LE.use_sqm = n
  
ip_address = <ip_address_of_the_SQM_LE>
  
port = 10001
  
write_log = y
  

in case you publish the allskycam and startrail images and timelapses videos in a remote website, you can do it by using an FTP transfer. If this is the case, configure the parameters as explained below.
  
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
  

 # 5. Test to check if it works:

from command line, just type:

python3 -m frankAllSkyCam

if it works, you should find the generated jpgs:

1. via browser, test http://<your_raspberry_IP>
2. /home/pi/frankAllSkyCam/img/<img_folder_with_date>/<jpg files>
3. on your remote FTP, in case you have configured it
  
==============================
  
Last step. If everything works, just make everything automatic. 
Type this command:

python3 -m frankAllSkyCam.crontab
  
==============================
  
  
Done !
enjoy it !
