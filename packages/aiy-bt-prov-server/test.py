#!/usr/bin/python3
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

import argparse
import logging
import logging.handlers
import os
import signal
import sys

from dhcpcd_client import DhcpcdClient
from p2p_wpas_client import P2pWpasClient
from sta_wpas_client import StaWpasClient

_closables = []


def _SignalHandler(signum, frame):
  print("\nCaught signal %d\n" % signum)
  for closable in _closables:
    closable.Close()


def _ExceptionHandler(exc_type, exc_value, exc_traceback):
  sys.__excepthook__(exc_type, exc_value, exc_traceback)
  os.kill(os.getpid(), signal.SIGINT)


def main():
  logger = logging.getLogger("logger")
  parser = argparse.ArgumentParser()
  parser.add_argument("--syslog", help="Log to syslog", action="store_true")
  parser.add_argument("--debug", help="Enable debug logging", action="store_true")
  parser.add_argument('rest', nargs=argparse.REMAINDER)
  args = parser.parse_args()
  if args.syslog:
    handler = logging.handlers.SysLogHandler(address = "/dev/log")
    format = "%s[%d]" % (sys.argv[0], os.getpid())
    formatter = logging.Formatter(format + ": %(message)s")
  else:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s: %(message)s')

  handler.setFormatter(formatter)
  logger.addHandler(handler)
  logger.setLevel(logging.INFO)

  if args.debug:
    logger.setLevel(logging.DEBUG)
    logger.info("Debug logs enabled")

  sta_wpas_client = StaWpasClient()
  p2p_wpas_client = P2pWpasClient()

  _closables.append(sta_wpas_client)
  _closables.append(p2p_wpas_client)

  sys.excepthook = _ExceptionHandler
  signal.signal(signal.SIGINT, _SignalHandler)
  signal.signal(signal.SIGTERM, _SignalHandler)

  def LogStatus():
    (wpa_state, ssid, ip, rssi) = sta_wpas_client.GetState()
    logger.info("State: %s SSID: '%s' IP: %s RSSI: %d" % (wpa_state, ssid, ip, rssi))

  LogStatus()

  if args.rest:
    if args.rest[0] == "scan":
      results = sta_wpas_client.Scan()
      logger.info("SSID".ljust(33) + " RSSI Secure")
      for entry in results:
        logger.info("%s%s  %s", entry["ssid"].ljust(33),
          str(entry["rssi"]).center(5), str(entry["secure"]))
    elif args.rest[0] == "connect":
      if len(args.rest) < 2:
        logger.error("connect: Missing SSID")
      else:
        ssid = args.rest[1]
        psk = None if len(args.rest) < 3 else args.rest[2]
        if sta_wpas_client.ConnectNetwork(ssid, psk):
          logger.info("Successfully connected to '%s'", ssid)
        else:
          logger.error("Failed to connect to '%s'", ssid)
        LogStatus()

  sta_wpas_client.Close()
  p2p_wpas_client.Close()


if __name__ == "__main__":
  main()
