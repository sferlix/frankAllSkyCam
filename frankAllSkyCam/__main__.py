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
from zoneinfo import ZoneInfo
from importlib import resources  # Python 3.7+
from configparser import ConfigParser
from frankAllSkyCam import fileManager, drawtext, getextdata, logos, calculateEphem, sqmreader, exposurecalc, autoexposure, starscalc, hotpixels, darksubtract, skystatus

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
night_mode = str(config['libcamera'].get('night_mode', '')).strip()
night_sharpness = str(config['libcamera'].get('night_sharpness', '0')).strip()
night_contrast = str(config['libcamera'].get('night_contrast', '1.0')).strip()

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
# exposure_mode and [auto_exposure] are optional: missing keys fall back to defaults.
exposure_mode = config.get('exposure', 'exposure_mode', fallback='sqm_based')
ae_target_mean = config.getfloat('auto_exposure', 'target_mean', fallback=30.0)
# target mean used in true night (sun below twilight_isp_backstop_deg); without the key
# it equals ae_target_mean, i.e. no boost.
ae_target_mean_dark_sky = config.getfloat('auto_exposure', 'target_mean_dark_sky', fallback=ae_target_mean)
ae_roi_percent = config.getfloat('auto_exposure', 'roi_percent', fallback=70.0)
ae_min_exposure_secs = config.getfloat('auto_exposure', 'min_exposure_secs', fallback=1.0)
ae_seed_exposure_secs = config.getfloat('auto_exposure', 'seed_exposure_secs', fallback=5.0)
# twilight handoff / saturation guard settings (see autoexposure.py)
ae_twilight_guard_deg = config.getfloat('auto_exposure', 'twilight_guard_deg', fallback=3.0)
# past this sun depression (default: astronomical twilight, as in calculateEphem) capture
# always uses the fixed-shutter exposure floor, never the ISP.
ae_twilight_isp_backstop_deg = config.getfloat('auto_exposure', 'twilight_isp_backstop_deg', fallback=18.0)
# exposure floor used between twilight_guard_deg and twilight_isp_backstop_deg
ae_twilight_min_exposure_secs = config.getfloat('auto_exposure', 'twilight_min_exposure_secs', fallback=0.02)
ae_twilight_ev_bias = config.getfloat('auto_exposure', 'twilight_ev_bias', fallback=0.3)
ae_saturation_clip_frac_threshold = config.getfloat('auto_exposure', 'saturation_clip_frac_threshold', fallback=0.05)
ae_saturation_severity_gain = config.getfloat('auto_exposure', 'saturation_severity_gain', fallback=8.0)
use_sqm_le = config['sqm']['use_sqm_le']

isFTP = str(config['ftp']['isFTP'])=='True'
FTP_server = str(config['ftp']['FTP_server'])
FTP_login = str(config['ftp']['FTP_login'])
FTP_pass = str(config['ftp']['FTP_pass'])
FTP_uploadFolder = str(config['ftp']['FTP_uploadFolder'])
FTP_fileNameAllSkyImg = str(config['ftp']['FTP_fileNameAllSkyImgJPG'])
FTP_fileName = FTP_uploadFolder + "/" + FTP_fileNameAllSkyImg
# optional: upload sky_status.json to the FTP server (off unless the customer enables it)
isFTPSkyStatus = config.getboolean('ftp', 'isFTPSkyStatus', fallback=False)
FTP_fileNameSkyStatus = config.get('ftp', 'FTP_fileNameSkyStatusJSON', fallback='')

tz = ZoneInfo(time_zone)
x = datetime.datetime.now(tz)

# only SQM measurement (its test shots use libcamera-still) and the capture need the camera;
# analysis, watermark, save and FTP run without the lock and may overlap the next run.
CAMERA_LOCK_PATH = logFolder + "/camera.lock"
CAMERA_LOCK_RETRY_SECS = 5
CAMERA_LOCK_MAX_WAIT_SECS = 90  # past this, assume the other run is stuck, not just slow

# ISP metadata sidecar for twilight-handoff frames; overwritten on every run
ISP_METADATA_PATH = logFolder + "/isp_metadata.json"

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
             print("WARNING: camera busy for " + str(waited) + "s - assuming the other run is stuck, killing the capture process")
             os.system("ps -ef|grep -E 'libcamera-still|rpicam-still' | grep -v color|awk '{print $2}'|xargs kill -9 1> /dev/null 2>&1")
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

def _logExecutionTime(start):
    # appends start, end and duration on every exit path of _run(); capture.log is
    # overwritten by each cron run, so it cannot show a trend
    end = datetime.datetime.now(tz)
    duration = round((end - start).total_seconds(), 1)
    print("Execution time: " + str(duration) + " secs")
    try:
       with open(logFolder + "/execution_time.log", "a") as f:
          f.write(start.isoformat() + "," + end.isoformat() + "," + str(duration) + "\n")
    except OSError as e:
       print("WARNING: could not append to execution_time.log: " + str(e))


def main():

    print("Execution started at: " +str(x))

    try:
       _run()
    finally:
       _logExecutionTime(x)


def _run():

    # ensure the darks folder exists (createAppFolders only creates it on a fresh install);
    # darksubtract and capturedarks need it
    fileManager.createPath(appPath + "darks")

    cameraLock = _acquireCameraLock()
    if cameraLock is None:
       print("Skipping this cycle - camera unavailable.")
       return

    data = calculateEphem.calculate(x)
    # full daytime: no SQM is computed; calculateExposure() returns 0 by day
    sqm, sqm_le = readsqm(daytime=not data["isTimelapse"])

    # twilight handoff (same test at dusk and dawn): while the sun is below the horizon and
    # the feedback loop's prediction is still under min_exposure_secs, the ISP auto-exposes.
    # twilight_guard_deg only guards against stale state right at the horizon crossing.
    sun_alt = data["sunAlt"]
    twilight_isp_mode = False
    exposure_min_secs = ae_min_exposure_secs
    # True in the -twilight_isp_backstop_deg..-twilight_guard_deg band: real fixed-shutter
    # capture, but twilight-bright, so cloud detection uses the texture-only signal.
    twilight_fixed_shutter_band = False
    if exposure_mode == "auto_exposure" and sun_alt < 0:
       if sun_alt >= -ae_twilight_guard_deg:
          twilight_isp_mode = True
       elif sun_alt <= -ae_twilight_isp_backstop_deg:
          # past astronomical twilight: always the normal fixed-shutter floor
          twilight_isp_mode = False
       else:
          # between the guard and the backstop: fixed shutter from the plain feedback-ratio
          # calculation (no ISP deferral) with the lower twilight_min_exposure_secs floor
          twilight_isp_mode = False
          exposure_min_secs = ae_twilight_min_exposure_secs
          twilight_fixed_shutter_band = True

    # target_mean boost only past astronomical twilight; the -3..-18 degree bands use the plain
    # ae_target_mean. At the dawn crossing the stored exposure state carries one step from
    # the boosted target back to the plain one (a bounded downward correction).
    target_mean = ae_target_mean
    if exposure_mode == "auto_exposure" and sun_alt <= -ae_twilight_isp_backstop_deg:
       target_mean = autoexposure.moon_adjusted_target_mean(
          ae_target_mean, ae_target_mean_dark_sky, data.get("moonAlt"), data.get("moonIllumination"))

    exposure = calculateExposure(sqm, twilight_isp_mode, sun_alt, exposure_min_secs, target_mean)

    data["sqm"] = sqm
    data["exposure"] = exposure
    data["inte"] = inte
    data["stars"] = 0
    data["clouds"] = 0

    calculateEphem.printData(data)


    jpg_file_name = fileManager.getOutputFileName(outputFolder, x) + data["suffisso"] + ".jpg"
    print("executing capture:")

    command = fileManager.getCameraBinary() + " -n -o " + jpg_file_name
    command += " --width " + str(horiz)
    command += " --height "+ str(vert)
    # twilight-handoff frames omit --immediate so the ISP's AGC/AWB converge before the
    # still is taken; every other mode keeps it
    if not twilight_isp_mode:
       command += " --immediate "
    if exposure >0:
       exposure = exposure * 1000000
       command +=" --shutter " + str(int(exposure)) + " "
       command += additional_night_params
       # --denoise cdn_hq enables the ISP's chroma-only denoise: it suppresses single-pixel
       # colour anomalies from hot/stuck photosites without touching luminance (stars). It
       # overrides any --denoise in additional_night_params.
       #
       # [libcamera] night_mode pins a sensor readout mode (empty: libcamera chooses);
       # night_sharpness and night_contrast set the ISP sharpness and contrast.
       if night_mode:
          command += " --mode " + night_mode
       command += " --denoise cdn_hq --sharpness " + night_sharpness + " --contrast " + night_contrast + " "
    else:
       if twilight_isp_mode:
          # twilight frame: the ISP auto-exposes and the values it chose are read back from its
          # metadata (any stale metadata file is removed first)
          try:
             os.remove(ISP_METADATA_PATH)
          except OSError:
             pass
          # centre-weighted metering instead of additional_day_params' --metering average: on a
          # fisheye the bright horizon ring would pull the ISP target down while the zenith is
          # still dark. Full daytime keeps --metering average.
          command += " --metering centre "
          command += " --metadata " + ISP_METADATA_PATH + " --metadata-format json "
          # --ev: small twilight-only bias on the ISP's metered target
          if ae_twilight_ev_bias:
             command += " --ev " + str(ae_twilight_ev_bias)
       else:
          command += additional_day_params

    try:
       #launch the command line
       print(command)
       os.system(command)

       print("Image captured")

       # release the camera lock: analysis, watermark, save and FTP don't use libcamera
       _releaseCameraLock(cameraLock)
       cameraLock = None

       extra_text = [""]
       if et_use =="y":
          #extra_text needed
          extra_string = getextdata.getData(et_data_file)
          extra_text = [extra_string, et_font_size, et_font_color, et_x_pos, et_y_pos]

       exposure_secs = exposure / 1000000.0 if exposure > 0 else None

       # twilight-handoff frame: harvest the exposure the ISP actually chose, for the
       # feedback loop and for cloud detection below
       harvested_exposure_secs = None
       if twilight_isp_mode:
          harvested_exposure_secs = autoexposure.record_isp_exposure(
             ISP_METADATA_PATH, jpg_file_name, appPath, roi_percent=ae_roi_percent)
          if harvested_exposure_secs is not None:
             data["exposure"] = harvested_exposure_secs

       if exposure_secs is not None:
          # dark-frame subtraction if a matching dark library exists (darksubtract.py), otherwise
          # the hot-pixel coordinate list (hotpixels.py); runs on the raw frame, before analysis
          # and the watermark
          if not darksubtract.applyToFile(jpg_file_name, appPath, exposure_secs,
                                           additional_night_params, night_mode,
                                           night_sharpness, night_contrast):
             hotpixels.applyToFile(jpg_file_name, appPath)

       # stars (night) and clouds (day or night); a twilight-handoff frame uses the ISP's
       # harvested exposure
       cloud_exposure_secs = exposure_secs if exposure_secs is not None else harvested_exposure_secs

       # with the sun below the horizon and no known exposure the ISP metered the capture
       # (calculateExposure() returns 0 for sq<9): those frames use the NRBR cloud signal
       # (twilight_isp_mode). twilight_fixed_shutter_band frames have a real but very short
       # exposure and use the texture-only signal instead.
       cloud_is_isp_driven = twilight_isp_mode or (cloud_exposure_secs is None and sun_alt < 0)
       print("calculating stars on: " + jpg_file_name)
       sst, scl  = starscalc.analyze_sky_robust(jpg_file_name, 0.65, 0.4, 30, exposure_secs=cloud_exposure_secs,
                                                 twilight_isp_mode=cloud_is_isp_driven,
                                                 twilight_fixed_shutter_band=twilight_fixed_shutter_band,
                                                 # lets the night star-deficit floor know the sky is dark and moonless
                                                 sun_alt_deg=sun_alt,
                                                 moon_factor=starscalc.moon_brightness_factor(
                                                    data.get("moonAlt"), data.get("moonIllumination")))
       data["stars"] = sst
       data["clouds"] = scl

       # hand this capture's sky numbers to skystatus (sqm and sst are 0 outside a night
       # exposure); never raises
       sky_status_written = skystatus.write_status(
          appPath, sqm, sst, scl, x, data["nightStartDt"], data["nightEndDt"],
          sun_rise=data["sunRiseDt"], sun_set=data["sunSetDt"],
          moon_rise=data["moonRiseDt"], moon_set=data["moonSetDt"],
          moon_illumination=data["moonIllumination"], moon_phase=data["moonPhaseName"])

       if exposure_secs is not None:
          # feed this run's raw (pre-watermark) frame into the auto-exposure state in every mode;
          # day captures are not tracked (the ISP exposes)
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
       # safety net: release the camera lock if an error skipped the release above
       _releaseCameraLock(cameraLock)

    time.sleep(1)

    # transfer files to your local web server folder
    if outputLocalWebFile != "":
       fileManager.saveToWEB(jpg_file_name, outputLocalWebFile)

    # transfer files to your FTP server
    fileManager.saveToFTP(isFTP, jpg_file_name,FTP_server,FTP_login,FTP_pass,FTP_fileName+".jpg")
    if sky_status_written:
       skystatus.upload_status(appPath, isFTPSkyStatus, isFTP, FTP_server, FTP_login, FTP_pass,
                               FTP_uploadFolder + FTP_fileNameSkyStatus if FTP_fileNameSkyStatus else "")

    print("AllSkyCam is done.")
    return

def readsqm(daytime=False):

   sq=0
   le =""
   try:

      sq, le  = sqmreader.readSQM(daytime=daytime)
   except Exception as e:
      # a failed read leaves sq=0, which reads as daytime; print the error so it can be diagnosed
      print("ERROR while calculating SQM: " + str(e))
   print("sqm = " + str(sq))
   print("sqm_le = " + str(le))
   return sq, le

def calculateExposure(sq, twilight_isp_mode=False, sun_alt=None, min_exposure_secs=None, target_mean=None):
   if min_exposure_secs is None:
      min_exposure_secs = ae_min_exposure_secs
   if target_mean is None:
      target_mean = ae_target_mean

   # sq<9 also occurs in below-horizon auto_exposure captures (the twilight bands), so it
   # cannot mean 'no exposure change needed' there as it does by day; the check uses
   # exposure_mode and sun_alt
   below_horizon_auto = exposure_mode == "auto_exposure" and sun_alt is not None and sun_alt < 0
   if sq < 9 and not below_horizon_auto:
      # no need to change the exposure.
      return 0

   # both predictions are computed on every run, whichever mode drives the capture
   # (including twilight_isp_mode and sq<9), so exposure_compare.csv always has both
   sqm_based_ex = exposurecalc.getExposure(sq, esp_secs=esp_secs, appPath=appPath)
   auto_ex = autoexposure.getExposure(sq, esp_secs=esp_secs, appPath=appPath,
                                       target_mean=target_mean,
                                       min_exposure_secs=min_exposure_secs,
                                       seed_exposure_secs=ae_seed_exposure_secs,
                                       saturation_clip_frac_threshold=ae_saturation_clip_frac_threshold,
                                       saturation_severity_gain=ae_saturation_severity_gain)

   if sq < 9 and not below_horizon_auto:
      # full daytime only: sq<9 keeps applied_ex at 0; the comparison row is still logged
      logExposureComparison(sq, sqm_based_ex, auto_ex, 0, twilight_isp_mode, target_mean)
      return 0

   ex = auto_ex if exposure_mode == "auto_exposure" else sqm_based_ex
   # esp_secs caps the applied exposure: applied_secs and data['exposure'] hold the capped
   # value, sqm_based_ex/auto_ex stay the raw model outputs. applied_ex is 0 in
   # twilight_isp_mode (the ISP exposes).
   applied_ex = 0 if twilight_isp_mode else min(ex, esp_secs)

   logExposureComparison(sq, sqm_based_ex, auto_ex, applied_ex, twilight_isp_mode, target_mean)

   return applied_ex

def logExposureComparison(sq, sqm_based_ex, auto_ex, applied_ex, twilight_isp_mode=False, target_mean=None):
   # target_mean: the target that drove auto_ex in this row, appended as a trailing column.
   # The header is written once, so older files keep their shorter header and readers must
   # accept rows of differing width.
   csv_path = logFolder + "/exposure_compare.csv"
   file_exists = os.path.exists(csv_path)
   capture_mode = "twilight_isp" if twilight_isp_mode else exposure_mode
   try:
      with open(csv_path, "a", newline="") as f:
         writer = csv.writer(f)
         if not file_exists:
            writer.writerow(["timestamp", "sqm", "exposure_mode", "capture_mode", "sqm_based_secs", "auto_exposure_secs", "applied_secs", "target_mean"])
         writer.writerow([datetime.datetime.now(tz).isoformat(), sq, exposure_mode, capture_mode, sqm_based_ex, auto_ex, applied_ex, target_mean])
   except Exception as e:
      print("WARNING: could not write exposure_compare.csv: " + str(e))


if __name__ == "__main__":
    main()

def outputDailyFolder():
   return outF

