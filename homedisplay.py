import os
import pygame
import pytz
from datetime import datetime, timedelta
from dateutil.tz import gettz
import requests
import urllib.request
import json
import signal
import traceback
import platform
import logging
import math
import getpass
from typing import Any

def is_windows():
    return platform.system() == "Windows"

def is_root():
    return getpass.getuser() == "root"

def is_pi():
    return platform.machine().startswith("arm")

if is_windows():
    logfile = "homedisplay.log"
elif is_root():
    logfile = "/var/log/homedisplay.log"
else:
    logfile = "/tmp/homedisplay.log"
logging.basicConfig(filename=logfile, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO)

def handler(signum: int, frame: Any) -> None:
    """Why is systemd sending sighups/SIGCONT? I DON'T KNOW."""
    logging.warning("Got a {} signal. Doing nothing".format(signum))
    # Note that this messes up the correct handling of 'service homedisplay stop' and restart. This means that the Pi
    # needs to be rebooted after changing the source.

if not is_windows():
    signal.signal(signal.SIGHUP, handler)
    signal.signal(signal.SIGCONT, handler)

bft_threshold = (0.3, 1.5, 3.4, 5.4, 7.9, 10.7, 13.8, 17.1, 20.7, 24.4, 28.4, 32.6)

def wind_bft(ms: float | None) -> int | None:
    "Convert wind from metres per second to Beaufort scale"
    if ms is None:
        return None
    for bft in range(len(bft_threshold)):
        if ms < bft_threshold[bft]:
            return bft
    return len(bft_threshold)

def get_secret(key: str) -> str | None:
    if is_windows():
        with open(f"d:\\Dropbox\\secrets\\{key}", "r") as f:
            return f.readline()
    else:
        return os.getenv(key)

class HomeDisplay:
    screen: pygame.Surface
    tz = pytz.timezone('Europe/Amsterdam')
    font_time: pygame.font.Font
    font_usage: pygame.font.Font
    font_temp: pygame.font.Font
    width: int = 0
    height: int = 0
    last_tomorrow_call: datetime | None = None
    temperature: int | str = '?'
    wind_speed: int | str = '?'
    wind_dir_name: str = '?'
    precipitations: list[int] = []
    
    def init_non_pi(self):
        pygame.init()
        self.width = 800
        self.height = 480
        self.screen = pygame.display.set_mode([self.width, self.height])

    def init_pi(self):
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
        if is_pi():
            self.init_pi()
        else:
            self.init_non_pi()

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


    def retrieve_weather_info(self):
        if self.last_tomorrow_call is None or datetime.now() >= self.last_tomorrow_call + timedelta(minutes=10):
            try:
                is_data_suspect = False
                try:
                    url = "https://api.open-meteo.com/v1/forecast"
                    querystring: dict[str, Any] = {
                        "latitude": 52.5028,   # Purmerend
                        "longitude": 4.9597,
                        "current": "temperature_2m,wind_speed_10m,wind_direction_10m",
                        "hourly": "precipitation",
                        "wind_speed_unit": "ms",
                        "forecast_hours": 12,
                        "timezone": "Europe/Amsterdam",
                    }

                    self.last_tomorrow_call = datetime.now()
                    r = requests.get(url, params=querystring)

                except requests.exceptions.ConnectionError:
                    logging.exception("Unable to connect to Open-Meteo API")
                    return

                if r.status_code != 200:
                    logging.warning(f"Open-Meteo API returned {r.status_code}")
                    return

                data = r.json()

                try:
                    self.temperature = round(data["current"]["temperature_2m"])
                except:
                    is_data_suspect = True

                try:
                    bft = wind_bft(data["current"]["wind_speed_10m"])
                    self.wind_speed = bft if bft is not None else '?'
                except:
                    is_data_suspect = True

                try:
                    wind_dir = data["current"]["wind_direction_10m"]
                    wind_index = int(((wind_dir + 360 / 16) % 360) / (360 / 16))
                    wind_dir_names = ["N", "NNO", "NO", "ONO", "O", "OZO", "ZO", "ZZO", "Z", "ZZW", "ZW", "WZW", "W", "WNW", "NW", "NWN"]
                    self.wind_dir_name = wind_dir_names[wind_index]
                except:
                    is_data_suspect = True

                if is_data_suspect:
                    logging.warning(f"Open-Meteo current data is suspect: {r.text}")

                logging.info(f"Measurements from Open-Meteo: {self.temperature}° {self.wind_speed} Bft {self.wind_dir_name}")

                try:
                    now = datetime.now(gettz("Europe/Amsterdam"))
                    current_hour_str = now.strftime("%Y-%m-%dT%H:00")
                    times = data["hourly"]["time"]
                    idx = times.index(current_hour_str) if current_hour_str in times else 0
                    self.precipitations = [round(p) for p in data["hourly"]["precipitation"][idx:idx + 6]]
                except:
                    is_data_suspect = True

                if is_data_suspect:
                    logging.warning(f"Open-Meteo hourly data is suspect: {r.text}")

            except:
                logging.exception("Unable to retrieve weather info from Open-Meteo")
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

        # Show net usage in the middle.
        live = self.get_live_usage()
        usage_text = "{0}W".format(int(live)) if live is not None else "?W"
        img = self.font_usage.render(usage_text, True, pygame.Color("white"))
        width = int((self.width - img.get_rect().w) / 2)
        height = int((self.height - img.get_rect().h) / 2 + 40)
        self.screen.blit(img, (width, height))

        try:
            self.show_weather_climacell()
        except Exception as e:
            # Do not let a failed call crash the display, but show the error.
            logging.warning(str(e))
            logging.warning(traceback.format_exc())

        pygame.display.update()

if os.path.exists("/sys/class/backlight/rpi_backlight/brightness"):
    # Set the brightness to a proper value
    with open("/sys/class/backlight/rpi_backlight/brightness", "w") as f:
        f.write("32")

home_display = HomeDisplay()
while (True):
    pygame.event.get()
    home_display.update()
    # Update every second because that's the interval that the smart meter updates.
    for i in range(10):
        pygame.event.get()
        pygame.time.wait(100)
