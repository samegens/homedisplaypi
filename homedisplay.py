import os
import pygame
import time
import random
import pytz
from datetime import datetime, timedelta, timezone
from dateutil.tz import gettz
import requests
import urllib.request
import json
import signal
import traceback
import platform
import logging
import math
from influxdb import InfluxDBClient
import dateutil


def is_windows():
    return platform.system() == "Windows"

if is_windows():
    logfile = "homedisplay.log"
else:
    logfile = "/var/log/homedisplay.log"
logging.basicConfig(filename=logfile, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO)

def handler(signum, frame):
    """Why is systemd sending sighups/SIGCONT? I DON'T KNOW."""
    logging.warning("Got a {} signal. Doing nothing".format(signum))
    # Note that this messes up the correct handling of 'service homedisplay stop' and restart. This means that the Pi
    # needs to be rebooted after changing the source.

if not is_windows():
    signal.signal(signal.SIGHUP, handler)
    signal.signal(signal.SIGCONT, handler)

bft_threshold = (0.3, 1.5, 3.4, 5.4, 7.9, 10.7, 13.8, 17.1, 20.7, 24.4, 28.4, 32.6)

def wind_bft(ms):
    "Convert wind from metres per second to Beaufort scale"
    if ms is None:
        return None
    for bft in range(len(bft_threshold)):
        if ms < bft_threshold[bft]:
            return bft
    return len(bft_threshold)

def get_secret(key):
    if is_windows():
        with open(f"d:\\Dropbox\\secrets\\{key}", "r") as f:
            return f.readline()
    else:
        return os.getenv(key)

class HomeDisplay :
    screen = None
    tz = pytz.timezone('Europe/Amsterdam')
    font_time = None
    font_usage = None
    font_temp = None
    width = 0
    height = 0
    last_tomorrow_call = None
    temperature = '?'
    wind_speed = '?'
    wind_dir_name = '?'
    precipitations = []
    
    def init_windows(self):
        pygame.init()
        self.width = 800
        self.height = 480
        self.screen = pygame.display.set_mode([self.width, self.height])

    def init_linux(self):
        "Initializes a new pygame screen using the framebuffer"
        # Based on "Python GUI in Linux frame buffer"
        # http://www.karoltomala.com/blog/?p=679
        disp_no = os.getenv("DISPLAY")
        if disp_no:
            logging.info("I'm running under X display = {0}".format(disp_no))
        
        # Check which frame buffer drivers are available
        # Start with fbcon since directfb hangs with composite output
        drivers = ['fbcon', 'directfb', 'svgalib']
        found = False
        for driver in drivers:
            # Make sure that SDL_VIDEODRIVER is set
            if not os.getenv('SDL_VIDEODRIVER'):
                os.putenv('SDL_VIDEODRIVER', driver)
            try:
                pygame.display.init()
            except pygame.error:
                logging.error('Driver: {0} failed.'.format(driver))
                continue
            found = True
            break
    
        if not found:
            raise Exception('No suitable video driver found!')
        
        size = (pygame.display.Info().current_w, pygame.display.Info().current_h)
        self.width = pygame.display.Info().current_w
        self.height = pygame.display.Info().current_h
        logging.info("Framebuffer size: %d x %d" % (size[0], size[1]))
        self.screen = pygame.display.set_mode(size, pygame.FULLSCREEN)

    def __init__(self):
        if is_windows():
            self.init_windows()
        else:
            self.init_linux()

        # Clear the screen to start
        self.screen.fill((0, 0, 0))        
        # Initialise font support
        pygame.font.init()
        self.font_time = pygame.font.SysFont(None, 96)
        self.font_usage = pygame.font.SysFont(None, 300)
        self.font_temp = self.font_time
        # Hide the mouse cursor
        pygame.mouse.set_visible(0)
        # Render the screen
        pygame.display.update()

        self.influxdb_client = InfluxDBClient('fitlet', 8086, 'admin', 'admin', 'hc2_log')

    def __del__(self):
        "Destructor to make sure pygame shuts down, etc."

    def test(self):
        # Fill the screen with red (255, 0, 0)
        red = (255, 0, 0)
        self.screen.fill(red)
        # Update the display
        pygame.display.update()

    def get_live_usage(self):
        # Retrieve the live usage from the meterkastpi.
        url = "http://meterkastpi/"
        req = urllib.request.Request(url)
        try:
            r = urllib.request.urlopen(req).read()
            cont = json.loads(r.decode('utf-8'))
            live = cont["live"]
            return live
        except Exception as e:
            # Do not let a failed call crash the display, but show the error.
            logging.warning(str(e))
            logging.warning(traceback.format_exc())

    def retrieve_indoor_temp_and_hum(self):
        records = self.influxdb_client.query("select * from \"hc2\" where \"room\"='Woonkamer' order by time desc limit 1;")
        for measurement in records.get_points():
            time = measurement["time"]
            time = dateutil.parser.isoparse(time)
            if (datetime.now(timezone.utc) - time).total_seconds() < 60 * 60:
                humidity = measurement["humidity"]
                temperature = measurement["temperature"]
                return (temperature, humidity)

        return None

    def show_indoor_temp_and_hum(self):
        result = self.retrieve_indoor_temp_and_hum()
        if result is None:
            return

        (temperature, humidity) = result
        text = f"{temperature}° {humidity:.0f}%"
        img = self.font_temp.render(text, True, (255, 255, 255))
        text_height = img.get_rect().h
        self.screen.blit(img, (0, text_height))

    def retrieve_weather_info(self):
        if self.last_tomorrow_call is None or datetime.now() >= self.last_tomorrow_call + timedelta(minutes=10):
            try:
                is_data_suspect = False
                try:
                    url = "https://api.tomorrow.io/v4/timelines"
                    querystring = {
                        "location": "6138471889c05400076aafc4", # Purmerend
                        "fields": ["temperature", "precipitationIntensity", "windSpeed", "windDirection"],
                        "units": "metric",
                        "timesteps": ["current", "1h"],
                        "startTime": datetime.now(gettz("Europe/Amsterdam")).isoformat(),
                        "endTime": (datetime.now(gettz("Europe/Amsterdam")) + timedelta(hours = 6)).isoformat(),
                        "apikey": get_secret("TOMORROW_API_KEY")
                    }

                    r = requests.request("GET", url, params=querystring)

                except requests.exceptions.ConnectionError:
                    logging.exception("Unable to connect to Tomorrow API")
                    # This call was not registered, so try again in the next update.
                    return

                if r.status_code != 200:
                    logging.warning(f"Tomorrow API returned {r.status_code}")
                    return;

                data = json.loads(r.text)

                try:
                    self.temperature = int(data["data"]["timelines"][0]["intervals"][0]["values"]["temperature"] + 0.5)
                except:
                    is_data_suspect = True

                try:
                    self.wind_speed = wind_bft(int(data["data"]["timelines"][0]["intervals"][0]["values"]["windSpeed"] + 0.5))
                except:
                    is_data_suspect = True

                try:
                    wind_dir = int(data["data"]["timelines"][0]["intervals"][0]["values"]["windDirection"] + 0.5)
                    wind_index = int(((wind_dir + 360 / 16) % 360) / (360 / 16))
                    wind_dir_names = ["N", "NNO", "NO", "ONO", "O", "OZO", "ZO", "ZZO", "Z", "ZZW", "ZW", "WZW", "W", "WNW", "NW", "NWN"]
                    self.wind_dir_name = wind_dir_names[wind_index]
                except:
                    is_data_suspect = True

                if is_data_suspect:
                    logging.warning(f"Tomorrow current data is suspect: {r.text}")

                logging.info(f"Measurements from Tomorrow: {self.temperature}° {self.wind_speed} Bft {self.wind_dir_name}")

                try:
                    self.precipitations = [int(d["values"]["precipitationIntensity"] + 0.5) for d in data["data"]["timelines"][1]["intervals"]]
                    is_data_suspect = False
                    if None in self.precipitations:
                        is_data_suspect = True

                except:
                    is_data_suspect = True

                if is_data_suspect:
                    logging.warning(f"Tomorrow 1h data is suspect: {r.text}")

                self.last_tomorrow_call = datetime.now()
            except:
                logging.exception("Unable to retrieve weather info from Tomorrow")
                self.temperature = "?"
                self.wind_speed = "?"
                self.wind_dir_name = "?"
                self.precipitations = []

    def show_weather_climacell(self):
        self.retrieve_weather_info()

        current_weather_text = f"{self.temperature}° {self.wind_speed} Bft {self.wind_dir_name}"
        img = self.font_temp.render(current_weather_text, True, (255, 255, 255))
        self.screen.blit(img, (0, 0))

        x_offset = 475
        y_offset = 7
        precipitation_max_height = 50
        precipitation_bar_width = 15
        precipitation_bar_spacing = 3
        color = (51, 204, 255)
        max_mm_hr = 5
        for precipitation in self.precipitations:
            if precipitation is None:
                precipitation = 0
            precipitation = min(precipitation, max_mm_hr)
            precipitation_bar_height = max(1, precipitation_max_height / max_mm_hr * math.ceil(precipitation))
            rect = (x_offset, y_offset + precipitation_max_height - precipitation_bar_height), (precipitation_bar_width, precipitation_bar_height)
            self.screen.fill(color, rect)
            x_offset += precipitation_bar_width + precipitation_bar_spacing

    def update(self):
        # Clear screen
        black = (0, 0, 0)
        self.screen.fill(black)

        # Show time and date in top right corner.
        now = datetime.now(self.tz)
        time_text = now.strftime("%H:%M")
        img = self.font_time.render(time_text, True, pygame.Color("white"))
        self.screen.blit(img, (self.width - img.get_rect().w, 0))
        text_height = img.get_rect().h

        date_text = datetime.now(self.tz).strftime("%d-%m")
        img = self.font_time.render(date_text, True, pygame.Color("white"))
        self.screen.blit(img, (self.width - img.get_rect().w, text_height))

        try:
            self.show_indoor_temp_and_hum()
        except Exception as e:
            # Do not let a failed call crash the display, but show the error.
            logging.warning(str(e))
            logging.warning(traceback.format_exc())

        # Show net usage in the middle.
        live = self.get_live_usage()
        usage_text = "{0}W".format(int(live)) if live is not None else "?W"
        img = self.font_usage.render(usage_text, True, pygame.Color("white"))
        self.screen.blit(img, ((self.width - img.get_rect().w) / 2, (self.height - img.get_rect().h) / 2 + 40))

        try:
            self.show_weather_climacell()
        except Exception as e:
            # Do not let a failed call crash the display, but show the error.
            logging.warning(str(e))
            logging.warning(traceback.format_exc())

        pygame.display.update()

if not is_windows():
    # Set the brightness to a proper value
    with open("/sys/class/backlight/rpi_backlight/brightness", "w") as f:
        f.write("32")

home_display = HomeDisplay()
while (True):
    pygame.event.get()
    home_display.update()
    # Update every 10 seconds because that's the interval that the smart meter updates.
    for i in range(100):
        pygame.event.get()
        pygame.time.wait(100)
