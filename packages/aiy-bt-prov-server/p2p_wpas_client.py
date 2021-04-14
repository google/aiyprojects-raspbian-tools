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

"""wpa_supplicant client for P2P interfaces."""
import logging
import os
import re
import threading
import time

from wpas_client import WpasClient

DEVICE_NAME = "AIY"


class P2pWpasClient(WpasClient):
  """wpa_supplicant client for P2P interfaces."""

  def __init__(self):
    self._logger = logging.getLogger("logger")
    self._lock = threading.Lock()
    self._state_change_cond = threading.Condition(self._lock)
    self._go_interface = None
    self._go_pending = False
    super(P2pWpasClient, self).__init__("wlan0")
    self.SendCommand("SET device_name %s" % DEVICE_NAME)
    self.SendCommand("P2P_SET ssid_postfix %s" % DEVICE_NAME)

  def Close(self):
    with self._lock:
      if self._go_interface is not None:
        self.RemoveP2pGroup(self._go_interface["ifname"])
    super(P2pWpasClient, self).Close()

  def StartP2pGo(self, timeout=120):
    res = None
    with self._lock:
      self._logger.info("%s: Creating P2P GO", self._ifname)
      start = time.monotonic()
      self._go_pending = self.CreateP2pGroup()
      while time.monotonic() - start < timeout:
        if not self._go_pending:
          self._RemoveAllP2pInterfaces()
          self._go_pending = self.CreateP2pGroup()
        to_wait = timeout - (time.monotonic() - start)
        self.SetAlarm("CHECK_GROUP", 5000)
        self._state_change_cond.wait(to_wait)

        if self._go_interface is not None:
          res = self._go_interface
          break

    return res

  def _RemoveAllP2pInterfaces(self):
    for ifname in os.listdir("/sys/class/net"):
      if ifname.startswith("p2p-" + self._ifname):
        res = self.RemoveP2pGroup(ifname)
        self._logger.info("%s: Removed %s: %s", self._ifname, ifname, res)

  def _OnEvent(self, event):
    with self._lock:
      if event.startswith("P2P-GROUP-STARTED"):
        self._logger.info("%s: %s", self._ifname, event)
        match = re.search(
            "P2P-GROUP-STARTED (.*) GO ssid=\"(.*)\" freq=\\d+ passphrase=\"(.*)\"",
            event)
        self._go_interface = {
            "ifname": match.group(1),
            "ssid": match.group(2),
            "psk": match.group(3)
        }
        self._go_pending = False
        self._logger.info("%s: P2P group started: %s", self._ifname,
                          self._go_interface["ifname"])
        self._state_change_cond.notifyAll()
      if event.startswith("P2P-GROUP-REMOVED"):
        self._logger.info("%s: %s", self._ifname, event)
        if self._go_interface is not None:
          match = re.search("P2P-GROUP-REMOVED (.*) GO reason=(.*)", event)
          # TODO: Close control interface
          self._go_interface = None

  def _OnAlarm(self, alarm):
    if alarm == "CHECK_GROUP":
      with self._lock:
        if self._go_interface is not None:
          return
        if self._go_pending:
          self._logger.info("%s: P2P group creation timed out", self._ifname)
          self._RemoveAllP2pInterfaces()
          self._go_pending = False
          self._state_change_cond.notifyAll()
