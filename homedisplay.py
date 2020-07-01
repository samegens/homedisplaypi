import os
import pygame
import time
import random
import pytz
from datetime import datetime, timedelta
import requests
import urllib.request
import json
import signal
import traceback
import platform
import logging
import pyowm
from climacell_api.client import ClimacellApiClient

def is_windows():
    return platform.system() == "Windows"

if is_windows():
    logfile = "homedisplay.log"
else:
    logfile = "/var/log/homedisplay.log"
logging.basicConfig(filename=logfile, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO)

def handler(signum, frame):
    """Why is systemd sending sighups/SIGCONT? I DON'T KNOW."""
    logging.warn("Got a {} signal. Doing nothing".format(signum))
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

class HomeDisplay :
    screen = None
    tz = pytz.timezone('Europe/Amsterdam')
    font_time = None
    font_usage = None
    font_sensor = None
    font_temp = None
    width = 0
    height = 0
    fibaro_to_name_list = [
        [ "Deursensor 4", "ach" ],                          # Achterdeur
        [ "Raamsensor 6", "woo" ],                          # Woonkamerraam
        [ "Raamsensor 7", "keu" ],                          # Keukenraam
        [ "Raamsensor 10", "bad" ],                         # Badkamerraam
        [ "Raamsensor 11", "Kat" ],                         # Kate slaapkamerraam
        [ "Raamsensor 5", "oud" ],                          # Ouderslaapkamerraam
        [ "Raamsensor 9", "wrk" ]                           # Werkkamerraam
    ]
    fibaro_to_name_map = dict(fibaro_to_name_list)
    devices_names = [x[0] for x in fibaro_to_name_list]
    sensor_status_width = 100
    sensor_status_height = 80
    owm = pyowm.OWM(os.getenv("OPENWEATHERMAP_API_KEY"))
    climacell_client = ClimacellApiClient(os.getenv("CLIMACELL_API_KEY"))
    last_climacell_call = None
    
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
        self.font_sensor = pygame.font.SysFont(None, 72)
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
        r = urllib.request.urlopen(req).read()
        cont = json.loads(r.decode('utf-8'))
        live = cont["live"]
        return live

    def get_window_door_sensor_status(self):
        user_name = urllib.parse.quote(os.getenv("FIBARO_USER_NAME") or "nobody")
        password = urllib.parse.quote(os.getenv("FIBARO_PASSWORD") or "secret")
        host = os.getenv("FIBARO_HOST") or "localhost"
        url = "http://{0}:{1}@{2}/api/devices".format(user_name, password, host)
        # We're using requests here, because urllib can't handle URLs that contain username and password.
        r = requests.get(url=url, headers={"X-Fibaro-Version": "2"})
        if r.status_code != 200:
            logging.warning("{0}: {1}".format(r.status_code, r.text))
            return None

        device_to_result_map = {}
        for device in r.json():
            name = device["name"]
            if name in self.devices_names:
                nl_name = self.fibaro_to_name_map[name]
                device_to_result_map[name] = {
                    "name": nl_name,
                    "is_open": device["properties"]["value"],
                    "battery_level": device["properties"]["batteryLevel"]
                }

        return device_to_result_map

    def show_window_door_sensor_status(self, device_to_result_map, sensor_name, x):
        rect = pygame.Rect((x, 480 - self.sensor_status_height), (self.sensor_status_width, self.sensor_status_height))
        color = (0, 255, 0)
        if device_to_result_map[sensor_name]["is_open"]:
            color = (255, 0, 0)
        self.screen.fill(color, rect)
        pygame.draw.rect(self.screen, (0, 0, 0), rect, 1)

        name = device_to_result_map[sensor_name]["name"]
        img = self.font_sensor.render(name, True, pygame.Color("white"))
        self.screen.blit(img, (rect.x + (rect.width - img.get_rect().w) / 2, rect.y + rect.height - img.get_rect().h))

        battery_main_width = 40
        battery_main_height = 20
        pygame.draw.rect(self.screen, (255, 255, 255), ((rect.x + rect.width - battery_main_width - 4, rect.y + 4), (battery_main_width, battery_main_height)), 3)
        battery_top_width = 5
        battery_top_height = 14
        battery_top_y_offset = (battery_main_height - battery_top_height) / 2
        pygame.draw.rect(self.screen, (255, 255, 255), 
                         ((rect.x + rect.width - battery_main_width - 4 - battery_top_width, rect.y + 4 + battery_top_y_offset), 
                          (battery_top_width, battery_top_height)))

        battery_level = int(device_to_result_map[sensor_name]["battery_level"])
        if battery_level == 255:
            battery_level = 0
        if battery_level > 5:
            battery_charge_width = int(battery_main_width / 100.0 * battery_level)
        pygame.draw.rect(self.screen, (255, 255, 255),
                         ((rect.x + rect.width - battery_charge_width - 4, rect.y + 4),
                          (battery_charge_width, battery_main_height)))
        pygame.draw.rect(self.screen, color, ((rect.x + rect.width - battery_main_width - 2, rect.y + 6), (battery_main_width - 4, battery_main_height - 4)), 1)

    def show_window_door_sensor_statuses(self):
        device_to_result_map = self.get_window_door_sensor_status()
        current_pos = 0
        for device_name in self.devices_names:
            self.show_window_door_sensor_status(device_to_result_map, device_name, current_pos)
            current_pos += self.sensor_status_width

    def show_weather_omw(self):
        mgr = self.owm.weather_manager()
        observation = mgr.weather_at_place('Purmerend,NL')
        weather = observation.weather

        temperatures = weather.temperature("celsius")
        current_temperature = int(temperatures["temp"])

        wind = weather.wind(unit = "beaufort")
        wind_speed = int(wind["speed"])
        wind_dir = int(wind["deg"])
        wind_index = int(((wind_dir + 360 / 16) % 360) / (360 / 16))
        wind_dir_names = ["N", "NNO", "NO", "ONO", "O", "OZO", "ZO", "ZZO", "Z", "ZZW", "ZW", "WZW", "W", "WNW", "NW" "NWN"]
        wind_dir_name = wind_dir_names[wind_index]

        current_weather_text = f"{current_temperature}° {wind_speed} Bft {wind_dir_name}"
        img = self.font_temp.render(current_weather_text, True, (255, 255, 255))
        self.screen.blit(img, (0, 0))

    def show_weather_climacell(self):
        if self.last_climacell_call is None or datetime.now() >= self.last_climacell_call + timedelta(minutes=10):
            r = self.climacell_client.realtime(lat=52.4953, lon=4.9373, fields=["temp", "wind_speed", "wind_direction"])
            if r.status_code != 200:
                logging.warning(f"Climacell API returned {r.status_code}")
                return;

            self.temperature = int(r.data().measurements["temp"].value)
            self.wind_speed = wind_bft(int(r.data().measurements["wind_speed"].value))
            wind_dir = int(r.data().measurements["wind_direction"].value)
            wind_index = int(((wind_dir + 360 / 16) % 360) / (360 / 16))
            wind_dir_names = ["N", "NNO", "NO", "ONO", "O", "OZO", "ZO", "ZZO", "Z", "ZZW", "ZW", "WZW", "W", "WNW", "NW" "NWN"]
            self.wind_dir_name = wind_dir_names[wind_index]

            logging.info(f"Measurements from Climacell: {self.temperature}° {self.wind_speed} Bft {self.wind_dir_name}")

            self.last_climacell_call = datetime.now()

        current_weather_text = f"{self.temperature}° {self.wind_speed} Bft {self.wind_dir_name}"
        img = self.font_temp.render(current_weather_text, True, (255, 255, 255))
        self.screen.blit(img, (0, 0))

    def update(self):
        # Clear screen
        black = (0, 0, 0)
        self.screen.fill(black)

        # Show time in top right corner.
        now = datetime.now(self.tz)
        time_text = now.strftime("%H:%M")
        img = self.font_time.render(time_text, True, pygame.Color("white"))
        self.screen.blit(img, (self.width - img.get_rect().w, 0))

        # Show net usage in the middle.
        live = self.get_live_usage()
        usage_text = "{0}W".format(int(live))
        img = self.font_usage.render(usage_text, True, pygame.Color("white"))
        self.screen.blit(img, ((self.width - img.get_rect().w) / 2, (self.height - img.get_rect().h) / 2))

        try:
            self.show_window_door_sensor_statuses()
        except Exception as e:
            # Do not let a failed call crash the display, but show the error.
            logging.warning(str(e))
            logging.warning(traceback.format_exc())

        self.show_weather_climacell()

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
