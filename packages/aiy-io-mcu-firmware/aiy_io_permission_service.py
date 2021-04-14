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

"""
Service for setting PWM pin permissions

When using the PWM Gpio the permission don't
get set so a non-sudo users can read or write to the
sysfs nodes.  Ideally this would be done using udev
alone about currently the act of exporting the pwm
pins does not generate events that we can trigger on.
We can trigger on loading of the module. So when we do
we set the proper permission on the export and unexport nodes.
For the individual pins we use inotify to determine when
changes are made to the pwmchipX. Then update the individual
pwmX nodes attributes permission as they become available.
"""

import sys
import os
import glob
import signal
import grp
import pwd
import itertools
import time
import logging
import inotify.adapters

log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
formatter = logging.Formatter(log_format)
ch.setFormatter(formatter)
logger.addHandler(ch)

pwm_path = '/sys/class/pwm'
pwm_chip_paths = glob.glob(os.path.join(pwm_path, 'pwmchip*'))

rootuid = pwd.getpwnam("root").pw_uid
grpuid = grp.getgrnam("gpio").gr_gid


def sigterm_handler(signo, stack_frame):
    logger.info("No longer monitoring pwmchips %s", str(pwm_chip_paths))
    sys.exit(0)


def monitor_paths(paths, block_duration=1.0, callback=None):
    logger.info("Watching path %s", paths)
    i = inotify.adapters.Inotify(paths=paths, block_duration_s=block_duration)
    try:
        for event in i.event_gen():
            if event is not None:
                (header, type_names, watch_path, filename) = event
                i.remove_watch(watch_path)
                if not callback is None:
                    callback(watch_path)
                i.add_watch(watch_path)

    finally:
        [i.remove_watch(path) for path in pwm_chip_paths]


def set_pwm_permissions(chip_path):
    time.sleep(0.05)
    logger.info("Setting permission for all nodes in %s", chip_path)
    pwm_pin_paths = glob.glob(os.path.join(chip_path, "pwm*"))
    pwm_nodes = list(
        itertools.chain.from_iterable(
            [glob.glob(os.path.join(path, "*")) for path in pwm_pin_paths]))

    logger.info("Found pwm dev nodes %s", str(pwm_nodes))
    if pwm_nodes:
        logger.info("Setting permissions on pwm pins %s", pwm_nodes)
        paths_to_update = pwm_pin_paths + pwm_nodes
        for path in paths_to_update:
            os.chown(path, rootuid, grpuid)
            os.chmod(path, 0o775)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, sigterm_handler)
    signal.signal(signal.SIGTERM, sigterm_handler)

    set_pwm_permissions(pwm_path)

    monitor_paths(pwm_chip_paths, 1.0, set_pwm_permissions)
