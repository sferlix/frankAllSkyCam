'''
  main program frankAllSkycam
  by Francesco Sferlazza, 2023
'''

import os
import sys
import csv
import fcntl
import datetime
from fractions import Fraction
import time
from pytz import timezone
from importlib import resources  # Python 3.7+
from configparser import ConfigParser
from frankAllSkyCam import fileManager, drawtext, getextdata, logos, calculateEphem, sqmreader, exposurecalc, autoexposure, starscalc

config = ConfigParser()
configFileName = fileManager.getConfigFileName()
config.read(configFileName)
appPath = os.path.expanduser("~") + "/frankAllSkyCam/"

time_zone = str(config['site']['time_zone'])
inte = str(config['site']['inte'])

logFolder = appPath + str(config['system']['logFolder'])
outputFolder = appPath + str(config['system']['otuputFolder'])
outputLocalWebFile = str(config['system']['outputLocalWebFile'])
horiz = str(config['resolution']['horiz'])
vert = str(config['resolution']['vert'])
rotation = int(config['resolution']['picture_rotation'])
picture_rotation = str(config['resolution']['picture_rotation'])

additional_night_params = str(config['libcamera']['additional_night_params'])
additional_day_params = str(config['libcamera']['additional_day_params'])

font_size   = int(config['font']['font_size'])
font_colorR = int(config['font']['font_colorR'])
font_colorG = int(config['font']['font_colorG'])
font_colorB = int(config['font']['font_colorB'])
font_color = [font_colorR,font_colorG,font_colorB]

top_left_x     = int(config['text_coords']['top_left_x'])
top_left_y     = int(config['text_coords']['top_left_y'])
top_right_x    = int(config['text_coords']['top_right_x'])
top_right_y    = int(config['text_coords']['top_right_y'])
bottom_left_x  = int(config['text_coords']['bottom_left_x'])
bottom_left_y  = int(config['text_coords']['bottom_left_y'])
bottom_right_x = int(config['text_coords']['bottom_right_x'])
bottom_right_y = int(config['text_coords']['bottom_right_y'])
top_center_x   = int(config['text_coords']['top_center_x'])
top_center_y   = int(config['text_coords']['top_center_y'])

text_positions = [[top_left_x,top_left_y],[top_right_x,top_right_y],[bottom_left_x,bottom_left_y],[bottom_right_x,bottom_right_y],[top_center_x,top_center_y]]

et_use         = str(config['extra_text']['et_use'])
et_data_file   = str(config['extra_text']['et_data_file'])
et_x_pos       = int(config['extra_text']['et_x_pos'])
et_y_pos       = int(config['extra_text']['et_y_pos'])
et_font_size   = int(config['extra_text']['et_font_size'])
et_font_colorR = int(config['extra_text']['et_font_colorR'])
et_font_colorG = int(config['extra_text']['et_font_colorG'])
et_font_colorB = int(config['extra_text']['et_font_colorB'])
et_font_color = [et_font_colorR,et_font_colorG,et_font_colorB]

compass_filename = str(config['compass']['compass_filename'])
compass_x_pos = int(config['compass']['compass_x_pos'])
compass_y_pos = int(config['compass']['compass_y_pos'])
compass_rot_angle = int(config['compass']['compass_rot_angle'])

logo_filename = str(config['logo']['logo_filename'])
logo_x_pos = int(config['logo']['logo_x_pos'])
logo_y_pos = int(config['logo']['logo_y_pos'])

phase_filename = str(config['moon_phase_img']['moon_filename'])
phase_x_pos = int(config['moon_phase_img']['moon_x_pos'])
phase_y_pos = int(config['moon_phase_img']['moon_y_pos'])

jupiter_x_pos = int(config['planets']['jupiter_x_pos'])
jupiter_y_pos = int(config['planets']['jupiter_y_pos'])
mars_x_pos = int(config['planets']['mars_x_pos'])
mars_y_pos = int(config['planets']['mars_y_pos'])
saturn_x_pos = int(config['planets']['saturn_x_pos'])
saturn_y_pos = int(config['planets']['saturn_y_pos'])
venus_x_pos = int(config['planets']['venus_x_pos'])
venus_y_pos = int(config['planets']['venus_y_pos'])

esp_secs = float(config['exposure']['esp_secs'])
# exposure_mode/[auto_exposure] are optional - fallback() keeps this working
# on existing config.txt files that predate this feature (no re-seeding).
exposure_mode = config.get('exposure', 'exposure_mode', fallback='sqm_based')
ae_target_mean = config.getfloat('auto_exposure', 'target_mean', fallback=30.0)
ae_roi_percent = config.getfloat('auto_exposure', 'roi_percent', fallback=70.0)
ae_min_exposure_secs = config.getfloat('auto_exposure', 'min_exposure_secs', fallback=1.0)
ae_seed_exposure_secs = config.getfloat('auto_exposure', 'seed_exposure_secs', fallback=5.0)
use_sqm_le = config['sqm']['use_sqm_le']

isFTP = str(config['ftp']['isFTP'])=='True'
FTP_server = str(config['ftp']['FTP_server'])
FTP_login = str(config['ftp']['FTP_login'])
FTP_pass = str(config['ftp']['FTP_pass'])
FTP_uploadFolder = str(config['ftp']['FTP_uploadFolder'])
FTP_fileNameAllSkyImg = str(config['ftp']['FTP_fileNameAllSkyImgJPG'])
FTP_fileName = FTP_uploadFolder + "/" + FTP_fileNameAllSkyImg

tz = timezone(time_zone)
x = datetime.datetime.now(tz)

# camera-exclusive section is SQM measurement (its own test shots also drive
# libcamera-still, via sqmreader's getPseudoSQM) through the main capture -
# nothing after that (analysis, watermark, save, FTP) touches the camera, so
# it deliberately runs lock-free and may overlap the next run's camera phase.
CAMERA_LOCK_PATH = logFolder + "/camera.lock"
CAMERA_LOCK_RETRY_SECS = 5
CAMERA_LOCK_MAX_WAIT_SECS = 90  # past this, assume the other run is stuck, not just slow

def _acquireCameraLock():
    fileManager.createPath(logFolder)
    fd = open(CAMERA_LOCK_PATH, "w")
    waited = 0
    while True:
       try:
          fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
          return fd
       except BlockingIOError:
          if waited >= CAMERA_LOCK_MAX_WAIT_SECS:
             print("WARNING: camera busy for " + str(waited) + "s - assuming the other run is stuck, killing libcamera")
             os.system("ps -ef|grep libcamera | grep -v color|awk '{print $2}'|xargs kill -9 1> /dev/null 2>&1")
             time.sleep(1)
             try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
             except BlockingIOError:
                print("ERROR: still could not get the camera lock after cleanup - skipping this cycle")
                fd.close()
                return None
          print("Camera busy (another run still capturing), waiting " + str(CAMERA_LOCK_RETRY_SECS) + "s...")
          time.sleep(CAMERA_LOCK_RETRY_SECS)
          waited += CAMERA_LOCK_RETRY_SECS

def _releaseCameraLock(fd):
    if fd is not None and not fd.closed:
       try:
          fcntl.flock(fd, fcntl.LOCK_UN)
       except OSError:
          pass
       fd.close()

def main():

    print("Execution started at: " +str(x))

    cameraLock = _acquireCameraLock()
    if cameraLock is None:
       print("Skipping this cycle - camera unavailable.")
       return

    data = calculateEphem.calculate(x)
    # full daytime (sun above horizon, isTimelapse False) never needs the
    # camera-based pseudo-SQM fallback: calculateExposure() always returns 0
    # regardless of sqm during the day, so estimating sky brightness via
    # camera test shots (getPseudoSQM -> takePicture) would only waste time.
    # A real SQM-LE hardware reading (cheap network call) still runs and still
    # gets logged during the day either way - only the pseudo fallback is
    # skipped, so a debug log row that would have carried a computed cSQM
    # comparison now carries 0 for that column during the day instead.
    sqm, sqm_le = readsqm(skip_pseudo=not data["isTimelapse"])
    exposure = calculateExposure(sqm)

    data["sqm"] = sqm
    data["exposure"] = exposure
    data["inte"] = inte
    data["stars"] = 0
    data["clouds"] = 0

    calculateEphem.printData(data)
    #max exposure (esp_secs from config.txt) wins over the calculated exposure
    if exposure > esp_secs:
       exposure = esp_secs


    jpg_file_name = fileManager.getOutputFileName(outputFolder, x) + data["suffisso"] + ".jpg"
    print("executing capture:")

    command = "libcamera-still -n -o " + jpg_file_name
    command += " --width " + str(horiz)
    command += " --height "+ str(vert)
    command += " --immediate "
    if exposure >0:
       exposure = exposure * 1000000
       command +=" --shutter " + str(int(exposure)) + " "
       command += additional_night_params
       # fixed at night regardless of additional_night_params: the ISP's default
       # sharpen/contrast are tuned for daylight video and actively work
       # against faint point sources (contrast stretch crushes a 1-2px star
       # toward black). --mode pins the sensor's true 2x2-binned full-FOV
       # readout (imx477: 2028x1520) instead of letting libcamera guess a mode
       # - binning sums photosite charge before quantization, giving real SNR
       # gain per pixel rather than a digital downscale of the full-res frame.
       # --denoise cdn_hq (rather than cdn_off) enables the ISP's colour-denoise
       # block - this is chrominance-only (it's the same setting rpicam-still's
       # "auto" mode already picks for stills) so it doesn't touch luminance/
       # spatial detail (i.e. star point sources), but it does suppress the
       # single-pixel colour anomalies from hot/stuck photosites that a long
       # night exposure (tens of seconds) at fixed high gain amplifies into
       # visible red dots. cdn_hq's throughput cost is irrelevant here since
       # this is a single still capture, not video/preview. Placed last so
       # these always win over any conflicting flag in additional_night_params.
       command += " --mode 2028:1520:12 --denoise cdn_hq --sharpness 0 --contrast 1.0 "
    else:
       command += additional_day_params

    try:
       #launch the command line
       print(command)
       os.system(command)

       print("Image captured")

       # release the camera lock now - nothing from here on (analysis,
       # watermark, save, FTP upload) touches libcamera, so it must not
       # block the next scheduled run's own SQM measurement/capture
       _releaseCameraLock(cameraLock)
       cameraLock = None

       extra_text = [""]
       if et_use =="y":
          #extra_text needed
          extra_string = getextdata.getData(et_data_file)
          extra_text = [extra_string, et_font_size, et_font_color, et_x_pos, et_y_pos]

       # calculate stars (night) and clouds (day or night)
       print("calculating stars on: " + jpg_file_name)
       exposure_secs = exposure / 1000000.0 if exposure > 0 else None
       sst, scl  = starscalc.analyze_sky_robust(jpg_file_name, 0.65, 0.4, 30, exposure_secs=exposure_secs)
       data["stars"] = sst
       data["clouds"] = scl

       if exposure_secs is not None:
          # feed this run's own raw (pre-watermark) frame back into the
          # auto-exposure state file, regardless of which mode is active,
          # so switching to auto_exposure later doesn't start cold. Day
          # captures (exposure_secs None) aren't tracked - the ISP drives
          # exposure itself in daylight, this feedback loop doesn't apply.
          autoexposure.recordExposureResult(jpg_file_name, exposure_secs, appPath, roi_percent=ae_roi_percent)


       photo = drawtext.printWatermark(data, jpg_file_name, font_size, font_color, sqm_le, rotation, text_positions, extra_text)

       images = {
           "logo": [logo_filename != "", logo_filename, logo_x_pos, logo_y_pos, 0],
           "phase":  [phase_filename != "", phase_filename, phase_x_pos, phase_y_pos, 0],
           "compass": [compass_filename != "", compass_filename, compass_x_pos, compass_y_pos, compass_rot_angle],
           "jupiter": [data["Jupiter"], "jupiter.png", jupiter_x_pos, jupiter_y_pos, 0],
           "mars": [data["Mars"], "mars.png", mars_x_pos, mars_y_pos, 0],
           "saturn": [data["Saturn"], "saturn.png", saturn_x_pos, saturn_y_pos, 0],
           "venus": [data["Venus"], "venus.png", venus_x_pos, venus_y_pos, 0]
       }

       print(images)
       photo = logos.imagesPaste(images, photo)
       photo.save(jpg_file_name, "jpeg")

       #generate /update alive.txt to say we are still alive
       textcommand = "touch " + logFolder +  "/alive.txt"
       os.system(textcommand)

       pass
    except:
       print("ERROR: " + str(sys.exc_info()[0]))
       pass
       return
    finally:
       # safety net - no-op if already released right after capture above;
       # guarantees the lock never leaks if an error occurred before that point
       _releaseCameraLock(cameraLock)
       z=datetime.datetime.now(tz)
       print("Execution time: " + str(abs(z-x).seconds) +" secs")

    time.sleep(1)

    # transfer files to your local web server folder
    if outputLocalWebFile != "":
       fileManager.saveToWEB(jpg_file_name, outputLocalWebFile)

    # transfer files to your FTP server
    fileManager.saveToFTP(isFTP, jpg_file_name,FTP_server,FTP_login,FTP_pass,FTP_fileName+".jpg")

    print("AllSkyCam is done.")
    return

def readsqm(skip_pseudo=False):

   sq=0
   le =""
   try:

      sq, le  = sqmreader.readSQM(skip_pseudo=skip_pseudo)
   except Exception as e:
      # bare "except: print(...)" (no message) used to swallow the actual
      # error, and left sq=0 - indistinguishable from a genuine full-daytime
      # reading, so a night-time read failure would silently be captured
      # with additional_day_params instead of night settings. Surfacing the
      # real exception at least makes that failure diagnosable in cron logs.
      print("ERROR while calculating SQM: " + str(e))
   print("sqm = " + str(sq))
   print("sqm_le = " + str(le))
   return sq, le

def calculateExposure(sq):
   if sq < 9:
      # no need to change the exposure.
      return 0

   # compute both predictions every time (the inactive one is cheap: pure
   # sqm math, or a JSON state-file read) so exposure_compare.csv always has
   # both sides for comparison, whichever mode is actually driving capture.
   sqm_based_ex = exposurecalc.getExposure(sq, esp_secs=esp_secs, appPath=appPath)
   auto_ex = autoexposure.getExposure(sq, esp_secs=esp_secs, appPath=appPath,
                                       target_mean=ae_target_mean,
                                       min_exposure_secs=ae_min_exposure_secs,
                                       seed_exposure_secs=ae_seed_exposure_secs)

   ex = auto_ex if exposure_mode == "auto_exposure" else sqm_based_ex

   logExposureComparison(sq, sqm_based_ex, auto_ex, ex)

   return ex

def logExposureComparison(sq, sqm_based_ex, auto_ex, applied_ex):
   csv_path = logFolder + "/exposure_compare.csv"
   file_exists = os.path.exists(csv_path)
   try:
      with open(csv_path, "a", newline="") as f:
         writer = csv.writer(f)
         if not file_exists:
            writer.writerow(["timestamp", "sqm", "exposure_mode", "sqm_based_secs", "auto_exposure_secs", "applied_secs"])
         writer.writerow([datetime.datetime.now(tz).isoformat(), sq, exposure_mode, sqm_based_ex, auto_ex, applied_ex])
   except Exception as e:
      print("WARNING: could not write exposure_compare.csv: " + str(e))


if __name__ == "__main__":
    main()

def outputDailyFolder():
   return outF

