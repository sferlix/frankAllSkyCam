This folder holds captured images, organized into per-day subfolders
(YYYYMMDD, rolling over at 08:00 rather than midnight), plus each day's
timelapse (timelapse_YYYYMMDD_night.mp4 / _24h.mp4) and startrail
(startrail_YYYYMMDD.jpg) once generated.

On a fresh install this folder is seeded empty; content appears once
captures start running. allskycamdelete.py prunes folders older than
days_retention (config.txt) automatically.
