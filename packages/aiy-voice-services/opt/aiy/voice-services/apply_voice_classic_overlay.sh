#!/bin/bash
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

UUID=0ddfb752-31be-4291-92da-73360695695e
FOUND_UUID=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
REBOOT=false
REBOOT_PULSE=false

if [ -f /proc/device-tree/hat/uuid ]; then
    FOUND_UUID=$(cat /proc/device-tree/hat/uuid | xargs -0)
else
    # No HAT found. However, this doesn't mean one isn't there: older Voice HATs
    # have unprogrammed EEPROMs which means they can't be recognized, so don't
    # adjust the config in this case.
    exit 0
fi

if [[ "$UUID" == "$FOUND_UUID" ]]; then
    if grep -q "^load-module module-suspend-on-idle" /etc/pulse/default.pa; then
        sed -i -e "s/^load-module module-suspend-on-idle/#load-module module-suspend-on-idle/" /etc/pulse/default.pa
        REBOOT_PULSE=true
    fi
    if grep -q "^# dtoverlay=googlevoicehat-soundcard" /boot/config.txt; then
        sed -i -e "s/^# dtoverlay=googlevoicehat-soundcard/dtoverlay=googlevoicehat-soundcard/" /boot/config.txt
        REBOOT=true
    elif ! grep -q "^dtoverlay=googlevoicehat-soundcard" /boot/config.txt; then
        echo "dtoverlay=googlevoicehat-soundcard" >> /boot/config.txt
        REBOOT=true
    fi
else
    if grep -q "^dtoverlay=googlevoicehat-soundcard" /boot/config.txt; then
        sed -i -e "s/^dtoverlay=googlevoicehat-soundcard/# \0/" /boot/config.txt
        REBOOT=true
    fi
    if grep -q "^#load-module module-suspend-on-idle" /etc/pulse/default.pa; then
        sed -i -e "s/^#load-module module-suspend-on-idle/load-module module-suspend-on-idle/" /etc/pulse/default.pa
        REBOOT_PULSE=true
    fi
fi

if [[ $REBOOT_PULSE == false ]]; then
    pulseaudio -k
    pulseaudio --start
fi

if [[ $REBOOT == true ]]; then
    reboot
fi
