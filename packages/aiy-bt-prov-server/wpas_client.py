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

"""wpa_supplicant control interface client."""
import logging
import os
import select
import socket
import sys
import tempfile
import threading
import time

WPAS_CTRL_DIR = "/var/run/wpa_supplicant"


class WpasClient(object):
  """wpa_supplicant control interface client."""

  def __init__(self, ifname, level=3):
    self._logger = logging.getLogger("logger")
    self._ifname = ifname
    self._control_lock = threading.Lock()
    with self._control_lock:
      self._event_thread = self._EventThread(self, ifname, level)
      self._control = self.InterfaceConnection(ifname)
      self._event_thread.start()

  def __del__(self):
    self.Close()

  def SendCommand(self, command):
    """Send command to wpa_supplicant."""
    with self._control_lock:
      return self._control.SendCommand(command)

  def Close(self):
    """Closes this instance and all related resources."""
    with self._control_lock:
      self._event_thread.Close()
      self._control.Close()

  def GetStatus(self):
    """Return current STATUS as a dictionary."""
    status = {}
    response = self.SendCommand("STATUS")
    for entry in response.strip().split("\n"):
      pos = entry.find("=")
      status[entry[0:pos]] = entry[pos + 1:]
    if "ssid" in status:
      status["ssid"] = self._DecodeSsid(status["ssid"])
    return status

  def GetSignal(self):
    """Return current SIGNAL as tuple."""
    signal = {}
    response = self.SendCommand("SIGNAL_POLL")
    if "FAIL" not in response:
      for entry in response.strip().split("\n"):
        pos = entry.find("=")
        signal[entry[0:pos]] = entry[pos + 1:]
    return signal

  def SaveConfig(self):
    """Saves current network configuration."""
    return "OK" in self.SendCommand("SAVE_CONFIG")

  def RequestScan(self):
    """Request a network scan to be initiated."""
    return "OK" in self.SendCommand("SCAN")

  def CheckCountryIsValid(self):
    """Check if the supplicant has a regulatory domain set, and set one if not."""
    country_valid = "FAIL" not in self.GetCountry()
    if not country_valid:
      self.SetCountry("US")

  def GetScanResults(self):
    """Returns a dict with the latest scan results available."""

    def _IsSecure(flags):
      return "WPA2-PSK" in flags or "WPA-PSK" in flags

    response = self.SendCommand("SCAN_RESULTS")

    results = {}
    for line in response.split("\n")[1:-1]:
      (_, _, rssi, flags, ssid) = line.split("\t")
      if not ssid:
        continue
      ssid = self._DecodeSsid(ssid)
      rssi = int(rssi)
      if not (ssid in results and rssi < results[ssid]["rssi"]):
        results[ssid] = {"ssid": ssid, "secure": _IsSecure(flags), "rssi": rssi}
    return list(results.values())

  def GetNetworks(self):
    """Returns all configured networks."""
    response = self.SendCommand("LIST_NETWORKS")

    networks = []
    for line in response.split("\n")[1:-1]:
      (net_id, ssid, bssid, flags) = line.split("\t")
      networks.append({
          "id": net_id,
          "ssid": ssid,
          "bssid": bssid,
          "flags": flags
      })
    return networks

  def GetNetworkBySsid(self, ssid):
    """Retrieves first network entry matching ssid."""
    for network in self.GetNetworks():
      if network["ssid"] == ssid:
        return network
    return None

  def RemoveNetwork(self, net_id):
    """Removes network with net_id."""
    return "OK" in self.SendCommand("REMOVE_NETWORK " + str(net_id))

  def EnableNetwork(self, net_id):
    """Enables network with net_id."""
    return "OK" in self.SendCommand("ENABLE_NETWORK " + str(net_id))

  def DisableNetwork(self, net_id):
    """Disables network with net_id."""
    return "OK" in self.SendCommand("DISABLE_NETWORK " + str(net_id))

  def SelectNetwork(self, net_id):
    """Selects network with net_id."""
    return "OK" in self.SendCommand("SELECT_NETWORK " + str(net_id))

  def AddNetwork(self):
    """Add a new network and return its net_id."""
    return int(self.SendCommand("ADD_NETWORK"))

  def SetNetworkSsid(self, net_id, ssid):
    """Set network ssid for net_id."""
    return self._SetNetworkProperty(net_id, "ssid", "\"%s\"" % ssid)

  def SetNetworkPsk(self, net_id, psk):
    """Set network psk for net_id."""
    return self._SetNetworkProperty(net_id, "psk", "\"%s\"" % psk)

  def SetNetworkScanSsid(self, net_id, scan):
    """Set scan_ssid for net_id (always scan before join)."""
    return self._SetNetworkProperty(net_id, "scan_ssid", int(scan))

  def SetNetworkKeyMgmt(self, net_id, secure):
    """Set network key_mgmt for net_id."""
    value = "WPA-PSK" if secure else "NONE"
    return self._SetNetworkProperty(net_id, "key_mgmt", value)

  def CreateP2pGroup(self):
    return "OK" in self.SendCommand("P2P_GROUP_ADD")

  def RemoveP2pGroup(self, ifname):
    return "OK" in self.SendCommand("P2P_GROUP_REMOVE " + ifname)

  def SetAlarm(self, alarm, delay):
    self._event_thread.SetAlarm(alarm, delay)

  def _SetNetworkProperty(self, net_id, prop, value):
    return "OK" in self.SendCommand("SET_NETWORK %d %s %s" % (net_id, prop,
                                                              value))
  def SetCountry(self, country):
    """Set the country for regulatory enforcement."""
    return "OK" in self.SendCommand("SET country %s" % country)

  def GetCountry(self):
    return self.SendCommand("GET country")

  def _DecodeSsid(self, ssid):
    # Undo the only explicit escapes wpa_supplicant does.
    ssid = ssid.replace("\\\\", "\\")
    ssid = ssid.replace("\\\"", "\"")
    ssid = ssid.replace("\\e", "\x45")
    ssid = ssid.replace("\\n", "\n")
    ssid = ssid.replace("\\r", "\r")
    ssid = ssid.replace("\\t", "\t")

    # ssid now only has printable ascii chars or \xNN escaped bytes.
    # Treat the entire thing as utf-8. SSID is just a byte sequence so
    # it doesn't have to be utf-8, but most non ascii cases are.
    buf = bytearray(b"")
    i = 0
    while i < len(ssid):
      if ssid[i:i + 2] == "\\x":
        buf.append(int(ssid[i + 2:i + 4], 16))
        i += 4
      else:
        buf.append(ord(ssid[i]))
        i += 1
    return buf.decode("utf-8")

  def _OnEvent(self, event):
    self._logger.info("Unhandled event (%s): %s" % (self._ifname, event))

  def _OnAlarm(self, alarm):
    self._logger.info("Unhandled alarm (%s): %s" % (self._ifname, alarm))

  class _EventThread(threading.Thread):
    """Thread polling and dispatching wpa_supplicant events."""

    def __init__(self, owner, ifname, level):
      threading.Thread.__init__(self)
      self._owner = owner
      self._level = level
      self._alarms = []
      self._alarm_lock = threading.Lock()
      self._monitor = owner.InterfaceConnection(ifname)
      self._closed = False

    def __del__(self):
      self.Close()

    def Close(self):
      self._closed = True
      self._monitor.Close()

    def SetAlarm(self, alarm, delay):
      with self._alarm_lock:
        self._alarms.append((time.monotonic() + delay / 1000, alarm))
        self._alarms.sort(key=lambda entry: entry[0])

    def run(self):
      try:
        self._monitor.Attach(self._level)
        while not self._closed:
          if self._monitor.HasPending(1):
            event = self._monitor.Receive()
            self._owner._OnEvent(event[3:])
          self._ProcessAlarms()

        self._monitor.Detach()
      except:  # Route to system hook, so pylint: disable=bare-except
        sys.excepthook(*sys.exc_info())

    def _ProcessAlarms(self):
      now = time.monotonic()
      with self._alarm_lock:
        if not self._alarms:
          return

        if self._alarms[0][0] > now:
          return

        def _IsExpired(entry):
          return True if now >= entry[0] else False

        expired = [a for a in self._alarms if _IsExpired(a)]
        self._alarms = [a for a in self._alarms if not _IsExpired(a)]

      for alarm in expired:
        self._owner._OnAlarm(alarm[1])

  class InterfaceConnection(object):
    """Connection to wpa_supplicant control interface socket."""
    _counter = 0

    @classmethod
    def _GetId(cls):
      res = cls._counter
      cls._counter += 1
      return res

    def __init__(self, ifname):
      self.started = False
      self.attached = False
      self_id = self._GetId()
      file_name = "wpasd_{}_{}_{}".format(str(os.getpid()), self_id, ifname)
      self.file = os.path.join(tempfile.gettempdir(), file_name)
      self._UnlinkFile()
      self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
      self.socket.bind(self.file)
      try:
        self.socket.connect(os.path.join(WPAS_CTRL_DIR, ifname))
      except OSError:
        self.socket.close()
        self._UnlinkFile()
        raise
      self.started = True

    def __del__(self):
      self.Close()

    def _UnlinkFile(self):
      try:
        os.unlink(self.file)
      except OSError:
        pass

    def Close(self):
      if self.attached:
        try:
          self.detach()
        except:  # We're closing, so pylint: disable=bare-except
          self.attached = False
      if self.started:
        self.socket.close()
        self._UnlinkFile()
        self.started = False

    def SendCommand(self, command):
      try:
        self.socket.send(command.encode("utf-8"))
      except OSError as error:
        if not self.started:
          raise error
        else:
          return ""
      [r, _, _] = select.select([self.socket], [], [], 10)
      if r:
        return self.Receive()
      raise Exception("SendCommand timeout")

    def Attach(self, level):
      if self.attached:
        return
      res = self.SendCommand("ATTACH")
      if "OK" in res:
        self.SendCommand("LEVEL " + str(level))
        self.attached = True
        return
      raise Exception("ATTACH failed")

    def Detach(self):
      if not self.attached:
        return
      while self.HasPending():
        self.Receive()
      res = self.SendCommand("DETACH")
      if "FAIL" not in res:
        self.attached = False
        return
      raise Exception("DETACH failed")

    def HasPending(self, timeout=0):
      [r, _, _] = select.select([self.socket], [], [], timeout)
      return True if r else False

    def Receive(self):
      return self.socket.recv(4096).decode("utf_8")
