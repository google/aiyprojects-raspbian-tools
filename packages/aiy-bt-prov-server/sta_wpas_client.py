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

"""wpa_supplicant client for STA interfaces."""
import re
import subprocess
import threading
import time

from dhcpcd_client import DhcpcdClient
from wpas_client import WpasClient


class StaWpasClient(WpasClient):
  """wpa_supplicant client for STA interfaces."""

  def __init__(self):
    self._lock = threading.Lock()
    self._scan_results_cond = threading.Condition(self._lock)
    self._state_change_cond = threading.Condition(self._lock)
    self._ass_ssid = ""
    self._dhcp_address = ""
    self._last_disabled_event = None
    self._status = {"wpa_state": "UNKNOWN"}
    with self._lock:
      super(StaWpasClient, self).__init__("wlan0")
      self._dhcpcd_client = self._NewIpDhcpcdClient("wlan0", self)
      self._UpdateSupplicantStatus()
    self.CheckCountryIsValid()
    self.RequestScan()

  def Close(self):
    with self._lock:
      self._dhcpcd_client.Close()
    super(StaWpasClient, self).Close()

  def GetState(self):
    with self._lock:
      return (self._status["wpa_state"], self._GetSsid(), self._dhcp_address,
              self._GetRssi())

  def WaitForNetwork(self, timeout=60):
    with self._lock:
      self._logger.info("%s: WaitForNetwork: initial state %s %s",
                        self._ifname, self._status["wpa_state"],
                        self._dhcp_address)
      def _IsConnected():
        return self._status["wpa_state"] == "COMPLETED" and self._dhcp_address

      if self._status["wpa_state"] == "INTERFACE_DISABLED":
        return False
      if _IsConnected():
        return True
      networks = self.GetNetworks()
      if not networks:
        self._logger.info("%s: WaitForNetwork: no networks", self._ifname)
        return False
      self._logger.info("%s: WaitForNetwork: waiting", self._ifname)

      start = time.monotonic()
      while not _IsConnected() and time.monotonic() - start < timeout:
        to_wait = timeout - (time.monotonic() - start)
        self._state_change_cond.wait(to_wait)

      self._logger.info("%s: WaitForNetwork: final state %s %s",
                        self._ifname, self._status["wpa_state"],
                        self._dhcp_address)
      return _IsConnected()

  def Scan(self, timeout=10):
    self._logger.info("%s: Requesting scan with timeout %s", self._ifname,
                      str(timeout))
    self._EnsureWifiOn()
    with self._lock:
      if self.RequestScan():
        self._scan_results_cond.wait(timeout)
    return self.GetScanResults()

  def ConnectNetwork(self, ssid, psk, timeout=20):
    self._EnsureWifiOn()
    self._logger.info("%s: Connecting to network '%s'" % (self._ifname, ssid))
    start = time.monotonic()
    with self._lock:
      network = self.GetNetworkBySsid(ssid)
      if network is not None:
        self._logger.info("%s: Network '%s' already exists, removing",
                          self._ifname, ssid)
        if not self.RemoveNetwork(network["id"]):
          self._logger.info("%s: Failed to remove network '%s' with id %d",
                            self._ifname, ssid, network["id"])

      for network in self.GetNetworks():
        self.DisableNetwork(network["id"])

      while time.monotonic() - start < timeout:
        if self._dhcp_address:
          self._logger.info("%s: Waiting for DHCP release of %s", self._ifname,
                            self._dhcp_address)
          to_wait = timeout - (time.monotonic() - start)
          self._state_change_cond.wait(to_wait)
        else:
          break
      if self._dhcp_address:
        self._logger.info("%s: DHCP %s not released", self._ifname,
                          self._dhcp_address)
        return False

      net_id = self.AddNetwork()
      self._logger.info("%s: Created network with id %d", self._ifname, net_id)

      secure = True if psk else False
      self.SetNetworkSsid(net_id, ssid)
      self.SetNetworkScanSsid(net_id, True)
      self.SetNetworkKeyMgmt(net_id, secure)
      if secure:
        self.SetNetworkPsk(net_id, psk)

      self._last_disabled_event = None
      self.SelectNetwork(net_id)
      self._logger.info("%s: Network '%s' with id %d selected", self._ifname,
                        ssid, net_id)

      while time.monotonic() - start < timeout:
        to_wait = timeout - (time.monotonic() - start)
        self._state_change_cond.wait(to_wait)
        state = self._status["wpa_state"]
        if self._last_disabled_event is not None:
          if self._last_disabled_event["id"] == net_id:
            reason = self._last_disabled_event["reason"]
            self._logger.info("%s: Network with id %d disabled with reason %s",
                              self._ifname, net_id, reason)
            break
        if state == "SCANNING":
          self._logger.info("%s: Scanning for '%s'", self._ifname, ssid)
        elif state == "ASSOCIATING":
          self._logger.info("%s: Associating with '%s'", self._ifname,
                            self._ass_ssid)
        elif state == "4WAY_HANDSHAKE":
          self._logger.info("%s: Authenticating with '%s'", self._ifname,
                            self._status["ssid"])
        elif state == "COMPLETED":
          if self._dhcp_address:
            self._logger.info("%s: Connected to '%s' with IP address %s",
                              self._ifname, self._status["ssid"],
                              self._dhcp_address)
            break
          else:
            self._logger.info("%s: Connected to '%s', waiting for IP address",
                              self._ifname, self._status["ssid"])

      if self._status["wpa_state"] == "COMPLETED" and self._dhcp_address:
        self._logger.info("%s: Connection attempt successful in %.1f s",
                          self._ifname,
                          time.monotonic() - start)
        self.SaveConfig()
        return True
      else:
        self._logger.info("%s: Connection attempt failed in %.1f s'",
                          self._ifname,
                          time.monotonic() - start)
        self.RemoveNetwork(net_id)
        return False

  def _GetSsid(self):
    ssid = None
    state = self._status["wpa_state"]
    if state == "ASSOCIATING":
      ssid = self._ass_ssid
    elif "ssid" in self._status:
      ssid = self._status["ssid"]
    return "" if ssid is None else ssid

  def _GetRssi(self):
    signal = self.GetSignal()
    return int(signal["RSSI"]) if "RSSI" in signal else 0

  def _EnsureWifiOn(self):
    subprocess.call("/usr/sbin/rfkill unblock wifi", shell=True)

  def _UpdateSupplicantStatus(self):
    new_status = self.GetStatus()
    state_changed = self._status["wpa_state"] != new_status["wpa_state"]
    self._status = new_status
    return state_changed

  def _OnEvent(self, event):
    if "Control interface command 'STATUS'" in event:
      return

    with self._lock:
      state_changed = self._UpdateSupplicantStatus()
      state = self._status["wpa_state"]

      if state_changed and state == "ASSOCIATING":
        state_changed = False
      if state != "ASSOCIATING":
        self._ass_ssid = ""
      if event.startswith("Trying to associate with "):
        match = re.search("\'(.*)\'", event)
        self._ass_ssid = self._DecodeSsid(match.group(1))
        state_changed = True

      if state_changed:
        self._logger.info("%s: New state: %s", self._ifname, state)
        self._state_change_cond.notifyAll()

      if event.startswith("CTRL-EVENT-SCAN-RESULTS"):
        self._scan_results_cond.notifyAll()

      if event.startswith("CTRL-EVENT-SSID-TEMP-DISABLED"):
        match = re.search(
            "id=(\\d+) ssid=\"(.*)\" auth_failures=(\\d+) duration=(\\d+) reason=(.*)",
            event)
        self._last_disabled_event = {
            "id": int(match.group(1)),
            "ssid": match.group(2),
            "auth_failures": int(match.group(3)),
            "duration": int(match.group(4)),
            "reason": match.group(5)
        }
        self._state_change_cond.notifyAll()

  def _OnNewIp(self, ip):
    self._logger.info("%s: DHCP: %s", self._ifname, ip if ip else "released")
    with self._lock:
      self._UpdateSupplicantStatus()
      self._dhcp_address = ip
      self._state_change_cond.notifyAll()

  class _NewIpDhcpcdClient(DhcpcdClient):

    def __init__(self, ifname, owner):
      self._owner = owner
      self._reported_ip = ""

      super(StaWpasClient._NewIpDhcpcdClient, self).__init__(ifname)

    def OnEvent(self, event):
      ip = self._reported_ip
      if ("if_up" in event and
          event["if_up"] == "false") or ("if_down" in event and
                                         event["if_down"] == "true"):
        ip = ""
      elif "new_ip_address" in event:
        ip = event["new_ip_address"]
      if ip != self._reported_ip:
        self._reported_ip = ip
        self._owner._OnNewIp(ip)
