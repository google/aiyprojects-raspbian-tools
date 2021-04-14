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

if [[ "$#" -ne 1 ]]; then
  echo "$0 <deb_dir>" >&2
  exit 1
fi

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DEB_DIR="$(cd "$1" && pwd)"
readonly PACKAGES=( \
    "${SCRIPT_DIR}/aiy-board-info" \
    "${SCRIPT_DIR}/aiy-bt-prov-server" \
    "${SCRIPT_DIR}/aiy-cwc-server" \
    "${SCRIPT_DIR}/aiy-io-mcu-firmware" \
    "${SCRIPT_DIR}/aiy-python-wheels" \
    "${SCRIPT_DIR}/aiy-usb-gadget" \
    "${SCRIPT_DIR}/aiy-voice-services" \
    "${SCRIPT_DIR}/aiy-projects-python/drivers/aiy" \
    "${SCRIPT_DIR}/aiy-projects-python/drivers/leds" \
    "${SCRIPT_DIR}/aiy-projects-python/drivers/overlays/vision" \
    "${SCRIPT_DIR}/aiy-projects-python/drivers/overlays/voice" \
    "${SCRIPT_DIR}/aiy-projects-python/drivers/pwm" \
    "${SCRIPT_DIR}/aiy-projects-python/drivers/sound" \
    "${SCRIPT_DIR}/aiy-projects-python/drivers/vision" \
)

function build_package {
  pushd "$1"
  local package=$(cat debian/control | grep Package | awk '{print $2}')
  dpkg-buildpackage -b -rfakeroot -us -uc -tc
  mv ../${package}*.deb ../${package}*.buildinfo ../${package}*.changes "${DEB_DIR}"
  popd
}

for package in "${PACKAGES[@]}"; do
  if [[ -n "${AIY_BUILD_PARALLEL}" ]]; then
    build_package "${package}" &
  else
    build_package "${package}"
  fi
done

cp "${SCRIPT_DIR}/aiy-vision-firmware_1.2-0_all.deb" \
   "${SCRIPT_DIR}/aiy-models_1.1-0_all.deb" \
   "${DEB_DIR}"

wait
