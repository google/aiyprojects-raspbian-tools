# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import subprocess
import threading

from gpiozero import Button
from gpiozero import LED

BLINK_ON_TIME_S = 0.5
BLINK_OFF_TIME_S = 0.5
BUTTON_HOLD_TIME_S = 5

BASE_GPIO_FILE = '/sys/module/gpio_aiy_io/drivers/platform:gpio-aiy-io/gpio-aiy-io/gpio/gpiochip*/base'
BASE_GPIO = int(subprocess.run('cat %s' % BASE_GPIO_FILE, shell=True, capture_output=True).stdout.strip())
BUTTON_GPIO = 23
BUTTON_LED_GPIO = 25

def _write(path, data):
  with open(path, 'w') as file:
    file.write(str(data))

class OnboardLED(object):
  def _run(self, on_time, off_time):
    gpio = BASE_GPIO + (13, 14)[self._led]
    _write('/sys/class/gpio/export', gpio)
    try:
      while not self._event.is_set():
        _write('/sys/class/gpio/AIY_LED%d/direction' % self._led, 'low')
        self._event.wait(on_time)
        _write('/sys/class/gpio/AIY_LED%d/direction' % self._led, 'high')
        self._event.wait(off_time)
    finally:
      _write('/sys/class/gpio/unexport', gpio)

  def __init__(self, led):
    self._led = led
    self._thread = None

  def blink(self, on_time, off_time):
    self._event = threading.Event()
    self._thread = threading.Thread(target=self._run, args=(on_time, off_time), daemon=True)
    self._thread.start()

  def off(self):
    if self._thread:
      self._event.set()
      self._thread.join()
      self._thread = None


class AiyTrigger(object):
  """Trigger interface for AIY kits."""

  def __init__(self, triggered):
    self._triggered = triggered
    self._active = False

    if os.path.exists('/sys/class/gpio/gpiochip%d' % BASE_GPIO):
      self._led = OnboardLED(0)
    else:
      self._led = LED(BUTTON_LED_GPIO)

    self._button = Button(BUTTON_GPIO, hold_time=BUTTON_HOLD_TIME_S)
    self._button.when_held = triggered

  def Close(self):
    self._led.off()

  def SetActive(self, active):
    if active:
      self._led.blink(on_time=BLINK_ON_TIME_S, off_time=BLINK_OFF_TIME_S)
    else:
      self._led.off()
