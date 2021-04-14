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

set -ex

if [ "$#" -ne 4 ]; then
    echo "$0 <build_info> <deb_dir> <python-dir> <overlay-dir>"
    exit 1
fi

readonly BUILD_INFO="$1"
readonly DEB_DIR="$2"
readonly PYTHON_DIR="$3"
readonly OVERLAY_DIR="$4"

readonly APT_NONINTERACTIVE="-y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"
export readonly DEBIAN_FRONTEND="noninteractive"
export readonly APT_KEY_DONT_WARN_ON_DANGEROUS_USAGE=yes

function install_package {
  local deb_file="$1"
  local package=$(dpkg-deb -f "${deb_file}" Package)
  local sha256=$(sha256sum "${deb_file}" | awk '{print $1}')
  local sha256_file="/tmp/${package}.sha256"

  if ! dpkg -l "${package}" ; then
    echo "Package ${package} is not installed."
    dpkg -i "${deb_file}"
    echo "${sha256}" > "${sha256_file}"
  else
    echo "Package ${package} is already installed."
    local installed_sha256="$(cat "${sha256_file}" 2>/dev/null || echo '')"
    if [[ "${installed_sha256}" != "${sha256}" ]]; then
      echo "Checksums do not ${package} match."
      dpkg --purge --force-all "${package}"
      dpkg -i "${deb_file}"
      echo "${sha256}" > "${sha256_file}"
    else
      echo "Checksums for ${package} match."
    fi
  fi
}

################################################################################
################################### root user ##################################
################################################################################

# Install python packages:
#   inotify                  (needed by aiy-io-mcu-firmware)
#   google-assistant-grpc    (needed by aiy-projects-python)
#   google-assistant-library (needed by aiy-projects-python)
#   google-cloud-speech      (needed by aiy-projects-python)
#   google-auth-oauthlib     (needed by aiy-projects-python)
#
# List needed packages excluding:
#   google-assistant-library (installed from aiy-python-wheels)
#   protobuf                 (installed from aiy-python-wheels)
#   argparse                 (part of python3 standard library)
#
# pip3 list --user --format=freeze | grep -v google-assistant-library | grep -v protobuf | grep -v argparse
time pip3 install --retries 10 --default-timeout=60 \
                  --no-deps --no-cache-dir --disable-pip-version-check \
                  -r /dev/stdin <<EOF
cachetools==4.1.1
enum34==1.1.10
google-api-core==1.23.0
google-assistant-grpc==0.3.0
google-auth==1.23.0
google-auth-oauthlib==0.4.2
google-cloud-speech==2.0.0
googleapis-common-protos==1.52.0
grpcio==1.33.2
inotify==0.2.10
libcst==0.3.13
nose==1.3.7
pathlib2==2.3.5
proto-plus==1.11.0
pyasn1==0.4.8
pyasn1-modules==0.2.8
pytz==2020.4
PyYAML==5.3.1
rsa==4.6
six==1.15.0
typing-extensions==3.7.4.3
typing-inspect==0.6.0
EOF

# Install debian packages
if ! ls /tmp/libttspico-utils_*.deb; then
  (cd /tmp && wget http://archive.raspberrypi.org/debian/pool/main/s/svox/libttspico-utils_1.0+git20130326-3+rpi1_armhf.deb)
fi

if ! ls /tmp/libttspico0_*.deb; then
  (cd /tmp && wget http://archive.raspberrypi.org/debian/pool/main/s/svox/libttspico0_1.0+git20130326-3+rpi1_armhf.deb)
fi

time apt ${APT_NONINTERACTIVE} install --fix-broken --no-upgrade raspberrypi-kernel-headers

time apt ${APT_NONINTERACTIVE} update && \
     apt ${APT_NONINTERACTIVE} install --fix-broken --no-upgrade \
  alsa-utils \
  avahi-utils \
  dkms \
  dnsmasq \
  pavucontrol \
  pulseaudio \
  python3-aiohttp \
  python3-bluez \
  python3-dbus \
  /tmp/libttspico-utils_*.deb \
  /tmp/libttspico0_*.deb

time apt ${APT_NONINTERACTIVE} remove \
  lxplug-volume

time apt ${APT_NONINTERACTIVE} autoremove

# Install general packages.
install_package $(ls ${DEB_DIR}/aiy-python-wheels_*.deb)
install_package $(ls ${DEB_DIR}/aiy-board-info_*_all.deb)
install_package $(ls ${DEB_DIR}/aiy-usb-gadget_*_all.deb)
install_package $(ls ${DEB_DIR}/aiy-io-mcu-firmware_*_all.deb)
install_package $(ls ${DEB_DIR}/aiy-bt-prov-server_*_all.deb)
install_package $(ls ${DEB_DIR}/aiy-cwc-server_*_all.deb)

# Install vision-specific packages.
install_package $(ls ${DEB_DIR}/aiy-models_*_all.deb)
install_package $(ls ${DEB_DIR}/aiy-vision-firmware_*_all.deb)

# Install kernel drivers.
install_package $(ls ${DEB_DIR}/leds-ktd202x-dkms_*.deb)
install_package $(ls ${DEB_DIR}/pwm-soft-dkms_*.deb)
install_package $(ls ${DEB_DIR}/aiy-dkms_*.deb)
install_package $(ls ${DEB_DIR}/aiy-vision-dkms_*.deb)
install_package $(ls ${DEB_DIR}/aiy-voicebonnet-soundcard-dkms_*.deb)
install_package $(ls ${DEB_DIR}/aiy-voice-services_*_all.deb)

# Install device tree overlays (in addition to EEPROM on the board).
install_package $(ls ${DEB_DIR}/aiy-overlay-vision_*.deb)
install_package $(ls ${DEB_DIR}/aiy-overlay-voice_*.deb)

# Setup aiyprojects apt repo.
echo "deb https://packages.cloud.google.com/apt aiyprojects-stable main" > /etc/apt/sources.list.d/aiyprojects.list
if ! apt-key list | grep "Google Cloud"; then
  curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -
fi

# Create build info.
echo "${BUILD_INFO}" > /etc/motd
echo "${BUILD_INFO}" > /etc/aiyprojects.info

# Enable SSH.
touch /boot/ssh

# Update boot configuration (/boot/config.txt).
sed -i -e "s/^dtparam=audio=on/#\0/" /boot/config.txt
sed -i -e "s/^dtparam=spi=on/#\0/" /boot/config.txt
grep -q "start_x=1" /boot/config.txt || echo "start_x=1" >> /boot/config.txt
grep -q "gpu_mem=128" /boot/config.txt || echo "gpu_mem=128" >> /boot/config.txt
grep -q "dtoverlay=spi0-1cs,cs0_pin=7" /boot/config.txt || echo "dtoverlay=spi0-1cs,cs0_pin=7" >> /boot/config.txt

# Update keyboard layout.
sed -i -e 's/"gb"/"us"/' /etc/default/keyboard

# Disable screen reader prompt
mv /usr/share/piwiz/srprompt.wav /usr/share/piwiz/srprompt.wav.bak

# Update PulseAudio config.
mkdir -p /etc/pulse/daemon.conf.d/
echo "default-sample-rate = 48000" > /etc/pulse/daemon.conf.d/aiy.conf

################################################################################
#################################### pi user ###################################
################################################################################

# Copy overlay.
tar -cf - -C "${OVERLAY_DIR}" --owner=pi --group=pi . | tar -xf - -C /

# Update desktop wallpaper.
mkdir -p /home/pi/.config/pcmanfm/LXDE-pi
sed "s:wallpaper=.*:wallpaper=/home/pi/.local/share/AIY-wallpaper.png:" \
               /etc/xdg/pcmanfm/LXDE-pi/desktop-items-0.conf > \
               /home/pi/.config/pcmanfm/LXDE-pi/desktop-items-0.conf
chown -R pi:pi /home/pi/.config

# Clone AIY python library.
readonly LOCAL_PYTHON_DIR=/home/pi/AIY-projects-python
rm -rf "${LOCAL_PYTHON_DIR}"
git clone "${PYTHON_DIR}" "${LOCAL_PYTHON_DIR}"
pushd "${LOCAL_PYTHON_DIR}"
git remote remove origin
git checkout -B aiyprojects
git remote add origin https://github.com/google/aiyprojects-raspbian
git config branch.aiyprojects.remote origin
git config branch.aiyprojects.merge refs/heads/aiyprojects
popd
chown -R pi:pi "${LOCAL_PYTHON_DIR}"

# Create symlinks.
ln -sf "${LOCAL_PYTHON_DIR}" /home/pi/AIY-voice-kit-python
chown -R pi:pi /home/pi/AIY-voice-kit-python
ln -sf /opt/aiy/models /home/pi/models
chown -R pi:pi /home/pi/models

# Setup joy detection demo service.
"${LOCAL_PYTHON_DIR}/src/examples/vision/joy/install-services.sh"

# Install AIY python library *globally*.
pip3 install --no-deps -e "${LOCAL_PYTHON_DIR}"
