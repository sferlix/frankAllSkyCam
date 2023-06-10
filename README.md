# frankAllSkyCam - AllSkyCam software 

Here is what you need to install, after ensuring to satisfy requirements (see below):

# `pip3 install frankAllSkyCam`


installation is done.
Launch the program:

`python3 -m frankAllSkyCam`

to configure your system, edit the single config.txt like this:

`nano /home/pi/frankAllSkyCam/config.txt`

details below. Enjoy !



# 1. Pre-requisites
prepare a clean SD card with the last version of raspbian. Lite version, without desktop is fine. 
The important point is that your OS must have the **libcamera** software (included in the last Raspberry OS).
The former version (raspistill) is not supported.If you want to check if you have libcamera installed, just type this command:

`libcamera-jpeg -o test.jpg --immediate -n`

you should find test.jpg in your current folder

Supposing you are fine with this pre-requisite, let's start

# 2. Ensure everything is updated:

```
sudo apt update
sudo apt upgrade
```
check you have pip installed (should be already in you raspberry):

`sudo apt install python3-pip`

done !

**Now you can install frankAllSkyCam**

`pip3 install frankAllSkyCam`

Now you have 2 options:

## 1. Use your Raspberry as a web server
Then, you need to have Apache installed. To do so, type this command:

`sudo apt install apache2 -y`

create the images folder in your web server.
```
sudo mkdir /var/www/html/img
```

I also provide you a very basic html page to show the allSky image. just move it into your local web server:

```
sudo mv /home/pi/frankAllSkyCam/index.html /var/www/html/
```


## 2. Upload your AllSkyCam to a webserver (e.g., via FTP)
In this case you need to configure your FTP parameters in the config.txt file (see below)

# 4. Configure your system

To configure your system, edit the single config.txt file:

`/home/pi/frankAllSkyCam/config.txt`

To edit the config.txt, you could use the nano editor:

`nano config.txt`

I would suggest to configure at least the following parameters:

```
inte = <name of your AllSkyCam that will be printed on top-center of the allSky images>
latitude = 44.73
longitude = 9.31
time_zone = Europe/Rome

```
in case you own the SQM-LE, ensure use_sqm =y and put the IP address and port of the SQM-LE:

```
use_sqm = y 
ip_address = <ip_address_of_the_SQM_LE>
port = 10001
write_log = n
```
 
in case you publish the allskycam, startrail images and timelapses videos in a remote website, you can do it by using an FTP transfer. If this is the case, configure the parameters as explained below.
  

```
parameters to configureFTP_server = <your_ftpserver.com>
FTP_login = your_user
FTP_pass = your_password 
FTP_uploadFolder =your_upload_dir
FTP_filenameAllSkyImgJPG = allskycam
FTP_fileNameStarTrailJPG = /startrails/starTrail.jpg
FTP_fileNameTimelapseMP4 = /videos/frankAllSkycam
 
```
allskycam_night.mp4 will be generated if nightTL = True
allskycam_24h.mp4 will be generated if fullTL = True`
if you do not want to use a remote FTP just set this way:
  
`isFTP=False`
  
There are many other options. The config.txt file is self-explanatory and you can customize many things, including logo, compass, extra-data you may want to print on your AllSkyCam image
  

 # 5. Test to check if it works:

from command line, just type:

`python3 -m frankAllSkyCam`

if it works, you should find the generated JPGs:

1. via browser, test http://<your_raspberry_IP>
2. /home/pi/frankAllSkyCam/img/<img_folder_with_date>/<jpg files>
3. on your remote FTP, in case you have configured it
  

==============================
  
# 6. Last step. 
  
If everything works, just make everything automatic. 
Type this command:

`python3 -m frankAllSkyCam.crontab`
  
it will install all the jobs
  
==============================
 
  
# For expert users 
  
You may want to customize your exposure time, depending on SQM values.
Pairs "(SQM value, exposure in secs)" are stored in this file:
   
 ` /home/pi/frankAllSkyCam/sqmexp.csv`
  
  (e.g., nano   /home/pi/frankAllSkyCam/sqmexp.csv)

So, if you wish to adjust it, you just need to change the exposure for every given SQM value. If you wish, you can also add more pairs (sqm values, secs).
 The software would predict the exposure duration by interpolating among existing values (polynomial regression grade=3).
 You may want calibrate your exposures and combine it with your desired --gain and --awbgains options (in config.txt)  
 In any case, the max exposure value will not exceed the esp_secs parameter in config.txt
  
 ================================== 
Done !
enjoy it !
