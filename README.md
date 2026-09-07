# frankAllSkyCam

Open-source AllSky camera software for a **Raspberry Pi + Pi HQ Camera** (or compatible libcamera sensor) with a fisheye lens. Point it at the sky, run it on a cron schedule, and it takes care of the rest:

- Captures a full-sky JPEG every minute or so, with exposure automatically driven by measured or estimated sky brightness (SQM), day or night.
- Watermarks each image with date/time, sun and moon rise/set times, moon phase, visible-planet icons, your own logo/compass, and any extra sensor data you want to show (weather station, temperature, humidity, ...).
- Estimates **cloud cover** and **star count** directly from the image, using different, purpose-built detection for daytime (blue-sky-vs-cloud color analysis) and nighttime (adaptive point-source detection that accounts for the Moon, trees/obstructions, and partial cloud).
- Builds nightly **timelapses** (night-only and/or full 24h) and a **startrail** image, and can upload everything to your own website via FTP.
- Optionally drives a **dew heater** (via a network relay or a GPIO-controlled one) based on the gap between internal temperature and dew point, to keep the lens clear.
- A watchdog reboots the Pi automatically if captures ever stall.

Everything runs unattended via cron, installed with a single command.

## Quick install

```
pip3 install frankAllSkyCam
```

On newer Raspberry Pi OS (Bookworm and later), `pip` may refuse a system-wide install; if so, use:

```
pip3 install frankAllSkyCam --break-system-packages
```

Then run it once to generate your config:

```
python3 -m frankAllSkyCam
```

This creates `~/frankAllSkyCam/` with a `config.txt` you'll want to edit before going further - see the full walkthrough below.

---

## 1. Prerequisites

Start from a clean, up-to-date Raspberry Pi OS (Lite is fine, no desktop needed):

```
sudo apt update
sudo apt upgrade
```

Make sure `pip` is available:

```
sudo apt install python3-pip
```

Install ImageMagick's development headers (needed to render the moon-phase image):

```
sudo apt install libmagickwand-dev
```

frankAllSkyCam uses **libcamera** (bundled with current Raspberry Pi OS). The older `raspistill` is not supported. Check libcamera works before going further:

```
libcamera-jpeg -o test.jpg --immediate -n
```

You should see it capture and leave a `test.jpg` in the current folder.

## 2. Install frankAllSkyCam

```
pip3 install frankAllSkyCam
```

This pulls in all required Python dependencies automatically (`numpy`, `ephem`, `Wand`, `opencv-python-headless`, `Pillow`, `requests`) - nothing else to install by hand. One thing to expect on a fresh Pi: `opencv-python-headless` doesn't always have a prebuilt wheel for every Raspberry Pi OS / Python version combination, and when pip has to fall back to building it from source, that single step can take a long time (tens of minutes) on a Pi. Let it run - it only happens once, not on every `pip install --upgrade`.

Then launch it once, so it can bootstrap your configuration:

```
python3 -m frankAllSkyCam
```

The first run creates:

```
~/frankAllSkyCam/
~/frankAllSkyCam/img/       (captured images, organized by day)
~/frankAllSkyCam/log/       (logs from every scheduled job)
~/frankAllSkyCam/sqm/       (SQM readings, if enabled)
~/frankAllSkyCam/png/       (logo, compass, moon/planet icons - customize freely)
~/frankAllSkyCam/tools/     (optional extras - see "Extra sensors" below)
~/frankAllSkyCam/config.txt
~/frankAllSkyCam/index.html
```

Any of these files can be freely edited - they live outside the installed package, so a future `pip install --upgrade frankAllSkyCam` will never overwrite your customizations. `png/` in particular is where you'd drop your own logo or compass image, matching the filenames already configured in `config.txt`.

## 3. Configure your system

Edit `~/frankAllSkyCam/config.txt` (e.g. `nano ~/frankAllSkyCam/config.txt`). At minimum, set:

```ini
[site]
inte = <name printed on top-center of the image>
latitude = 44.75
longitude = 9.29
elevation = 1150
time_zone = Europe/Rome
```

If you own a **SQM-LE** sky-quality meter, point to it under `[sqm]` (otherwise leave `use_sqm_le = n` and the software estimates SQM from the image itself):

```ini
[sqm]
use_sqm_le = n
ip_address = <ip_address_of_the_SQM_LE>
port = 10001
sqmLog = n
```

### Hosting the image

**Option A - the Pi serves it locally**, via Apache:

```
sudo apt install apache2 -y
sudo mkdir -p /var/www/html/img
sudo mv ~/frankAllSkyCam/index.html /var/www/html/
```

For a full gallery-style site (timelapses, startrails, sky map) rather than just the bare image, grab the `website/` folder from this repository - plain HTML + JS, no PHP required.

**Option B - upload to an external website via FTP.** Configure `[ftp]` in `config.txt`:

```ini
[ftp]
isFTP = True
FTP_server = your_ftpserver.com
FTP_login = your_username
FTP_pass = your_password
FTP_uploadFolder = /your_folder/
FTP_filenameAllSkyImgJPG = /img/allskycam
FTP_fileNameTimelapseMP4 = /video/frankAllSkycam
FTP_fileNameStarTrailJPG = /startrail/startrail.jpg
```

Leave `isFTP = False` if you don't want any remote upload.

### Timelapses

```ini
[timelapse]
nightTL = True   # allskycam_night.mp4, sunset to sunrise
fullTL = True    # allskycam_24h.mp4, full day
```

By default the video is smoothed on generation, since captures a minute or more apart otherwise make stars visibly "jump" frame to frame rather than glide:

```ini
smoothMotion = True   # tblend frame-blend for smoother apparent star motion
deflicker = True      # smooths frame-to-frame exposure/brightness variation
```

Both are cheap (no motion estimation, unlike ffmpeg's `minterpolate`, which is too slow on a Pi over hundreds of frames and prone to ghosting on noisy starfields) and safe to leave on. `config.txt`'s `ffmpeg2`/`ffmpeg3` remain a free-form expert escape hatch for extra encoder flags, but the software already applies its own `-vf` for scaling plus these two filters - if you add your own `-vf`/`-filter:v` there, set `smoothMotion`/`deflicker` to `False` first, since ffmpeg errors out on a duplicate `-vf` flag rather than merging them.

`config.txt` is fully commented - text position, font/color, logo/compass/planet icon placement, and max night exposure (`esp_secs`) are all in there and safe to tweak.

## 4. Test it

```
python3 -m frankAllSkyCam
```

If it worked, you'll find the generated JPEG:

1. In a browser, at `http://<your_raspberry_IP>` (if you set up Apache)
2. At `~/frankAllSkyCam/img/<YYYYMMDD>/<file>.jpg`
3. On your remote FTP host, if configured

## 5. Automate it

```
python3 -m frankAllSkyCam.crontab
```

This installs every scheduled job for you: captures (every minute, day and night), a watchdog every 15 minutes, nightly startrail and timelapse generation, daily old-image cleanup, and a periodic ephemeris refresh. Re-run it any time (e.g. once a year) to refresh the sunrise/sunset-based capture windows.

A capture that runs long (a slow exposure, or a slow FTP upload) is safe to overlap with the next scheduled one: an internal lock only ever covers the camera-touching part of a run (SQM measurement through the shot itself) - never analysis, watermarking, saving, or upload, none of which touch the camera. If the camera is still genuinely busy when the next run starts, it waits (up to 90s) rather than skipping or colliding with the capture in progress; past that, it assumes the other run is stuck and clears it before proceeding.

Every job's output goes to its own log file under `~/frankAllSkyCam/log/`, so if anything misbehaves, that's the first place to check. Each file holds only the most recent run's output (overwritten every time, not appended) - `capture.log` in particular would otherwise grow forever given how often captures run.

### Enjoy it!

---

## Extra sensors, weather stations, and the dew heater

`~/frankAllSkyCam/tools/` holds small, independent scripts meant for **you to edit** - they live outside the installed package specifically so a `pip install --upgrade` never touches your customizations.

- **`generateExtraData.py`** collects data from your own devices (a weather station, a Shelly smart plug, an I2C temperature/humidity sensor, ...) and writes a single text string that gets watermarked onto the image (enable it via `et_use = y` under `[extra_text]` in `config.txt`). Several ready-made helper functions are included (Ecowitt/WS90-style JSON stations, a Davis Vantage Pro2 plaintext feed, Shelly devices) - uncomment and configure the ones you have in `getData()`.
- **`generateExtraData.conf`**, sitting next to it, holds your device URLs/IPs and credentials - kept separate from the main `config.txt` on purpose, so this file can be handed to (or edited by) someone who only needs to touch sensor settings.
- The same file can also **switch a dew heater on/off**, based on `(internal temperature - dew point)`, reusing whatever sensor readings you already fetch for the watermark text (no extra network calls). It supports either a network relay (e.g. a Shelly) or a relay wired directly to a Raspberry Pi GPIO pin - see the `[dew_heater]` section in `generateExtraData.conf`.

Both are wired into the crontab automatically by `python3 -m frankAllSkyCam.crontab`.

## For expert users

Exposure duration is predicted from SQM via a small polynomial model, trained from real-world `(SQM, exposure seconds)` pairs stored in:

```
~/frankAllSkyCam/sqmexp.csv
```

Add or adjust pairs to retune the curve for your own site/camera/gain settings - the software interpolates (degree-3 polynomial regression) between the values you provide. The `esp_secs` parameter in `config.txt` always caps the maximum exposure regardless of what the model predicts.

You can also fully customize the `libcamera-still` invocation via `additional_night_params` / `additional_day_params` in `config.txt` - gain, white balance, anything `libcamera-still` accepts (just don't set `--shutter`, `--immediate`, `--mode`, `--denoise`, `--sharpness` or `--contrast` there - those are fixed by frankAllSkyCam at night, since the ISP's daylight-tuned defaults for denoise/sharpen/contrast actively suppress faint stars, and `--mode` pins a true 2x2-binned, full-FOV sensor readout for better low-light sensitivity per pixel - not just a wider `--gain`).

### Alternative exposure strategy: auto_exposure

By default (`exposure_mode = auto_exposure` in `config.txt`'s `[exposure]` section) each run measures the previous capture's own brightness (inside a circular ROI - `[auto_exposure] roi_percent`, excluding fixed dark obstructions near the frame edges) and adjusts the next exposure toward `target_mean`, with no `sqmexp.csv` calibration needed. It reacts a run late to fast sky changes (clouds moving in, moonrise) since the feedback is carried across runs via a small state file, not live. Setting `exposure_mode = sqm_based` switches back to predicting exposure from the pre-calibrated SQM curve above instead. Whichever mode is active, both predictions are logged side by side to `~/frankAllSkyCam/log/exposure_compare.csv` every run, so you can compare them before committing to a switch.

Note this default only applies to a fresh install - if you're upgrading an existing install, your `config.txt` keeps whatever it already has (nothing overwrites it), so add `exposure_mode = auto_exposure` under `[exposure]` yourself if you want to switch.

**Twilight handoff (auto_exposure only):** `min_exposure_secs` stops the feedback loop from collapsing exposure toward zero once it's genuinely dark - but forced blindly right at sunset/sunrise, it used to produce a badly overexposed frame every dusk and dawn, before the loop had a chance to learn the sky was still twilight-bright. Now, while the sun is below the horizon but the loop's own honest prediction is still under `min_exposure_secs`, libcamera's own auto-exposure drives that capture instead (same as daytime), and its real result is harvested to keep the feedback loop warm for when it does take over - the same check applies at both dusk and dawn, sized by the sky's actual measured brightness rather than a fixed clock, so it holds up under real cloud cover too. `[auto_exposure] twilight_guard_deg` is only a cold-start safety strip near the horizon, not what sizes the handoff.

**Saturation guard (auto_exposure only):** if a previous frame came back significantly clipped (a cloud reflecting light pollution at night, say), the plain brightness ratio can't tell how far over target it really was - a clipped mean looks the same whether the true overexposure was 2x or 30x. `[auto_exposure] saturation_clip_frac_threshold` / `saturation_severity_gain` control when and how much harder the next exposure gets cut in that case.

## Requirements

Installed automatically via pip: `numpy`, `ephem`, `Wand`, `opencv-python-headless`, `Pillow`, `requests`. Python 3.9+. See the note under [Install frankAllSkyCam](#2-install-frankallskycam) about `opencv-python-headless` sometimes needing a slow source build on a Pi.

If you use the optional sensor examples in `tools/generateExtraData.py` that read Raspberry Pi hardware directly (CPU temperature, an I2C sensor, GPIO-driven relays), they rely on `gpiozero`, `smbus`/`smbus2`, and `RPi.GPIO` - all pre-installed on Raspberry Pi OS, no extra steps needed.

## Uninstalling

```
pip3 uninstall frankAllSkyCam --break-system-packages
```

This removes only the installed package. It does **not** remove:

- `~/frankAllSkyCam/` - your `config.txt`, captured images, logs, and SQM data. Kept outside the package on purpose, so a `pip install --upgrade` never overwrites your customizations - but that also means an uninstall never touches it.
- The cron jobs `python3 -m frankAllSkyCam.crontab` installed.

If you want a clean removal (e.g. before reinstalling from scratch), remove both yourself:

```
crontab -l | grep -v '#frankAllSkyCam-managed' | crontab -
rm -rf ~/frankAllSkyCam
```

## License

GPLv3 - see [LICENSE](LICENSE).
