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
import threading
import time

import RPi.GPIO as GPIO

BLINK_ON_TIME_S = 0.5
BLINK_OFF_TIME_S = 0.5
BUTTON_HOLD_TIME_S = 5

BUTTON_GPIO = 23
BUTTON_LED_GPIO = 25

BASE_GPIO = 497
LED1_GPIO = BASE_GPIO + 14

def _write(path, data):
  with open(path, 'w') as file:
    file.write(str(data))

class LED(object):
  def _button_led_loop(self, on_time, off_time):
    GPIO.setup(BUTTON_GPIO, GPIO.OUT)
    while not self._event.is_set():
      GPIO.output(BUTTON_LED_GPIO, True)
      self._event.wait(on_time)
      GPIO.output(BUTTON_LED_GPIO, False)
      self._event.wait(off_time)

  def _onboard_led_loop(self, on_time, off_time):
    _write('/sys/class/gpio/export', LED1_GPIO)
    try:
      while not self._event.is_set():
        _write('/sys/class/gpio/AIY_LED1/direction', 'low')
        self._event.wait(on_time)
        _write('/sys/class/gpio/AIY_LED1/direction', 'high')
        self._event.wait(off_time)
    finally:
      _write('/sys/class/gpio/unexport', LED1_GPIO)

  def __init__(self):
    self._thread = None

  def blink(self, on_time, off_time):
    self._event = threading.Event()

    if os.path.exists('/sys/class/gpio/gpiochip%d' % BASE_GPIO):
      run = self._onboard_led_loop
    else:
      run = self._button_led_loop

    self._thread = threading.Thread(target=run, args=(on_time, off_time), daemon=True)
    self._thread.start()

  def off(self):
    if self._thread:
      self._event.set()
      self._thread.join()
      self._thread = None

class Button(object):
  def __init__(self, delay, callback):
    GPIO.setup(BUTTON_GPIO, GPIO.IN)

    self._thread = threading.Thread(target=self._run, args=(delay, callback), daemon=True)
    self._thread.start()

  def _run(self, delay, callback):
    while True:
      GPIO.wait_for_edge(BUTTON_GPIO, GPIO.FALLING)
      start = time.monotonic()
      time.sleep(0.2)  # Debounce

      done = callback
      while time.monotonic() - start < delay:
        if GPIO.input(BUTTON_GPIO):
          done = None
          break
        time.sleep(0.01)

      if done:
        done()

class AiyTrigger(object):
  """Trigger interface for AIY kits."""

  def __init__(self, triggered):
    GPIO.setmode(GPIO.BCM)

    self._led = LED()
    self._button = Button(BUTTON_HOLD_TIME_S, triggered)

  def Close(self):
    self._led.off()

  def SetActive(self, active):
    if active:
      self._led.blink(on_time=BLINK_ON_TIME_S, off_time=BLINK_OFF_TIME_S)
    else:
      self._led.off()
