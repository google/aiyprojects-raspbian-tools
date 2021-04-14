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

"""DHCPCD socket client."""
import logging
import os
import select
import socket
import struct
import sys
import tempfile
import threading

DHCPCD_SOCK = "/var/run/dhcpcd.unpriv.sock"


class DhcpcdClient(object):
  """DHCPCD socket client."""

  def __init__(self, ifname):
    self._logger = logging.getLogger("logger")
    self.event_thread = self._EventThread(self, ifname)
    self.event_thread.start()
    self.ifname = ifname

  def __del__(self):
    self.Close()

  def Close(self):
    self.event_thread.Close()

  def OnEvent(self, event):
    self._logger.info("Unhandled event (%s): %s", self._ifname, event)

  class _EventThread(threading.Thread):
    """Thread waiting on and dispatching DHCPCD events."""

    def __init__(self, owner, ifname):
      threading.Thread.__init__(self)
      self.owner = owner
      self.ifname = ifname
      self.monitor = self._MonitorConnection()
      self.closed = False

    def __del__(self):
      self.Close()

    def Close(self):
      self.closed = True
      self.monitor.Close()

    def run(self):
      try:
        while not self.closed:
          if self.monitor.HasPending(1):
            event = self.monitor.ReceiveEvent()
            if event["interface"] == self.ifname:
              self.owner.OnEvent(event)
      except:  # Route to system hook, so pylint: disable=bare-except
        sys.excepthook(*sys.exc_info())

    class _MonitorConnection(object):
      """Connection to DHCPCD monitor interface."""

      _counter = 0

      @classmethod
      def _GetId(cls):
        res = cls._counter
        cls._counter += 1
        return res

      def __init__(self):
        self.started = False
        self_id = self._GetId()
        file_name = "wpasd_{}_{}_dhcpcd".format(str(os.getpid()), self_id)
        self.file = os.path.join(tempfile.gettempdir(), file_name)
        self._UnlinkFile()
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(self.file)
        try:
          self.socket.connect(DHCPCD_SOCK)
        except:
          self.socket.close()
          self._UnlinkFile()
          raise
        self.started = True
        self.SendCommand("--getinterfaces")
        self.socket.recv(4)
        self.SendCommand("--listen")

      def __del__(self):
        self.Close()

      def _UnlinkFile(self):
        try:
          os.unlink(self.file)
        except OSError:
          pass

      def Close(self):
        if self.started:
          self.socket.close()
          self._UnlinkFile()
          self.started = False

      def SendCommand(self, command):
        self.socket.send(command.encode("utf-8"))

      def HasPending(self, timeout=0):
        [r, _, _] = select.select([self.socket], [], [], timeout)
        return True if r else False

      def ReceiveEvent(self):
        buf = self.socket.recv(4)
        num_bytes = struct.unpack("@I", buf)[0]
        buf = self.socket.recv(num_bytes)
        buf = buf.split(b"\x00")

        event = {}
        entries = [entry.decode("utf-8").split("=") for entry in buf if b"=" in entry]
        for entry in entries:
          event[entry[0]] = entry[1]
        return event
