# frankAllSkyCam - AllSkyCam software 

Here is what you need to install, *after ensuring to satisfy requirements* (see below):

# `pip3 install frankAllSkyCam`


installation is done, but you still need to configure some parameters, according to your preferences.
To do so, launch the program:

`python3 -m frankAllSkyCam`

It will create some folders and the config.txt file. Now, you can start the configuration.
Edit the single config.txt like this:

`nano /home/pi/frankAllSkyCam/config.txt`

details below. Enjoy !



# 1. Pre-requisites
Prepare a clean SD card with the last version of raspbian. Lite version, without desktop is fine. 

Ensure everything is updated:
```
sudo apt update
sudo apt upgrade
```
check you have pip installed (should be already in your Raspberry Pi distribution):

`sudo apt install python3-pip`

Install ImageMagick:

`sudo apt-get install libmagickwand-dev`

frankAllSkyCam uses the **libcamera** software (included in the last Raspberry OS). The former version (raspistill) is not supported. If you want to check if you have libcamera installed, just type this command:

`libcamera-jpeg -o test.jpg --immediate -n`

you should see the libcamera operating and, at the end, you should find test.jpg in your current folder.

Supposing you are fine with the pre-requisites, let's start !

# 2. Install frankAllSkyCam

`pip3 install frankAllSkyCam`

Now you have need to launch program, so that installation will be complete.

The first execution will create some folders:

```
/home/pi/frankAllSkyCam
/home/pi/frankAllSkyCam/img
/home/pi/frankAllSkyCam/log
/home/pi/frankAllSkyCam/sqm
/home/pi/frankAllSkyCam/png
```

and will generate some files:

```
/home/pi/frankAllSkyCam/config.txt   
/home/pi/frankAllSkyCam/index.html
```
config.txt contains your preferences.

The png folder will contain some image files that you may personalize (e.g., logo and compass), together with other png files such as moon and planets.

Now you just need to configure your preferences. See below.

# 2. Configure your system
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

It's time to decide if your Raspberry Pi will work also as a web server.

## 1. Use your Raspberry as a web server
Then, you need to have Apache (or other web server) installed. To do so, type this command:

`sudo apt install apache2 -y`

create the images folder in your web server. Example:

```
sudo mkdir /var/www/html/img
```
After the installation, you will find a very basic `index.html` page to show just the allSky image. 
Just move the index.html file into your local web server:

```
sudo mv /home/pi/frankAllSkyCam/index.html /var/www/html/
```
If you want a "real" website, please download it from this repository, `website` folder. It's just html + Javascript. No php needed.

## 2. You will use an external web server.

In this case, you may want to upload your AllSkyCam.jpg to an external webserver (e.g., via FTP)
To do so, you need to configure your FTP parameters in the config.txt file (see below)
 
```
isFTP=True
FTP_server = <your_ftpserver.com>
FTP_login = your_user
FTP_pass = your_password 
FTP_uploadFolder =your_upload_dir
FTP_filenameAllSkyImgJPG = allskycam
FTP_fileNameStarTrailJPG = /startrails/starTrail.jpg
FTP_fileNameTimelapseMP4 = /videos/frankAllSkycam
```

According to the above configuration, the allskycam, startrail images and timelapses videos will be uploaded on a remote website, via FTP.
Of course, if you do not want to use a remote FTP just set `isFTP=False`

An additional parameter will enable / disable the generation of the timelapses:

```
nightTL = True
fullTL = True
```

allskycam_night.mp4 will only show the night timelapse, from sunset to suntise and will be generated if `nightTL = True`

allskycam_24h.mp4 will be showing th 24h and will be generated if `fullTL = True`

There are some other options. The config.txt file is self-explanatory and you can customize many things, including logo, compass, extra-data you may want to print on your AllSkyCam image (eg info coming from your sensors, your meteo station if any).
  

 # 3. Test to check if it works:

from command line, just type:

`python3 -m frankAllSkyCam`

if it works, you should find the generated JPGs:

1. via browser, test http://<your_raspberry_IP>
2. /home/pi/frankAllSkyCam/img/<img_folder_with_date>/<jpg files>
3. on your remote FTP, in case you have configured it
 
  
# 4. Last step. 
  
If everything works, just make everything automatic. 
Type this command:

`python3 -m frankAllSkyCam.crontab`
  
it will install all the jobs ! 

### Enjoy it !
 
  
## For expert users 
  
This software calculates the exposure time thanks to a machine learning algorithm I have trained to derive the SQM. Even it is not needed at all, You may want to customize your exposure time, depending on SQM values.
Pairs "(SQM value, exposure in secs)" are stored in this file:
   
 ` /home/pi/frankAllSkyCam/sqmexp.csv`
  
  (e.g., nano   /home/pi/frankAllSkyCam/sqmexp.csv)

So, if you wish to adjust it, you just need to change the exposure for every given SQM value. If you wish, you can also add more pairs (sqm values, secs).
 The software would predict the exposure duration by interpolating among existing values (polynomial regression grade=3).
 
 You may want customize your libcamera settings, according to your camera and preferences. For example, you can change your --gain and --awbgains options (in config.txt) and add additional libcamera options.
 
 In any case, the max exposure value will not exceed the esp_secs parameter in config.txt
  
