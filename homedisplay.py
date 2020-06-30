import os
import pygame
import time
import random
import pytz
from datetime import datetime
import requests
import urllib.request
import json
import signal
import traceback
import platform
import logging

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

class HomeDisplay :
    screen = None
    tz = pytz.timezone('Europe/Amsterdam')
    font = None
    font_usage = None
    font_sensor = None
    width = 0
    height = 0
    fibaro_to_name_list = [
        [ "Deursensor 4", "Achterdeur" ],
        [ "Raamsensor 6", "Woonkamerraam" ],
        [ "Raamsensor 7", "Keukenraam" ],
        [ "Raamsensor 10", "Badkamerraam" ],
        [ "Raamsensor 11", "Kate slaapkamerraam" ],
        [ "Raamsensor 5", "Ouderslaapkamerraam" ],
        [ "Raamsensor 9", "Werkkamerraam" ]
    ]
    fibaro_to_name_map = dict(fibaro_to_name_list)
    devices_names = [x[0] for x in fibaro_to_name_list]
    sensor_status_width = 100
    sensor_status_height = 80
    
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
        self.font = pygame.font.SysFont(None, 96)
        self.font_usage = pygame.font.SysFont(None, 300)
        self.font_sensor = pygame.font.SysFont(None, 72)
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
                    "is_open": device["properties"]["value"]
                }

        return device_to_result_map

    def show_window_door_sensor_status(self, device_to_result_map, sensor_name, sensor_abbreviation, x):
        rect = pygame.Rect((x, 480 - self.sensor_status_height), (self.sensor_status_width, self.sensor_status_height))
        color = (0, 255, 0)
        if device_to_result_map[sensor_name]["is_open"]:
            color = (255, 0, 0)
        self.screen.fill(color, rect)
        pygame.draw.rect(self.screen, (0, 0, 0), rect, 1)

        img = self.font_sensor.render(sensor_abbreviation, True, pygame.Color("white"))
        self.screen.blit(img, (rect.x + (rect.width - img.get_rect().w) / 2, rect.y + (rect.height - img.get_rect().h) / 2))

    def show_window_door_sensor_statuses(self):
        device_to_result_map = self.get_window_door_sensor_status()
        current_pos = 0
        self.show_window_door_sensor_status(device_to_result_map, "Deursensor 4", "ach", current_pos)
        current_pos += self.sensor_status_width
        self.show_window_door_sensor_status(device_to_result_map, "Raamsensor 6", "woo", current_pos)
        current_pos += self.sensor_status_width
        self.show_window_door_sensor_status(device_to_result_map, "Raamsensor 7", "keu", current_pos)
        current_pos += self.sensor_status_width
        self.show_window_door_sensor_status(device_to_result_map, "Raamsensor 10", "bad", current_pos)
        current_pos += self.sensor_status_width
        self.show_window_door_sensor_status(device_to_result_map, "Raamsensor 11", "Kat", current_pos)
        current_pos += self.sensor_status_width
        self.show_window_door_sensor_status(device_to_result_map, "Raamsensor 5", "oud", current_pos)
        current_pos += self.sensor_status_width
        self.show_window_door_sensor_status(device_to_result_map, "Raamsensor 9", "wrk", current_pos)
        current_pos += self.sensor_status_width

    def update(self):
        # Clear screen
        black = (0, 0, 0)
        self.screen.fill(black)

        # Show time in top right corner.
        now = datetime.now(self.tz)
        time_text = now.strftime("%H:%M")
        img = self.font.render(time_text, True, pygame.Color("white"))
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
    pygame.time.wait(10000)
