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
   echo "$0 <out_dir>" >&2
   exit 1
fi

readonly OUT_DIR="$1"

readonly RASPBIAN_IMAGE_URL=${RASPBIAN_IMAGE_URL:-https://downloads.raspberrypi.org/raspios_armhf/images/raspios_armhf-2021-03-25/2021-03-04-raspios-buster-armhf.zip}
readonly RASPBIAN_IMAGE=${RASPBIAN_IMAGE_URL##*/}
readonly BUILD_ENGINE="${BUILD_ENGINE:-docker}"

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly BUILD_SCRIPTS_DIR="${SCRIPT_DIR}/../scripts/"
readonly DEB_DIR="${OUT_DIR}/deb"

if [[ "$OSTYPE" == "darwin"* ]]; then
  readonly MD5SUM=gmd5sum
  readonly SHA256SUM=gsha256sum
else
  readonly MD5SUM=md5sum
  readonly SHA256SUM=sha256sum
fi

mkdir -p "${DEB_DIR}"

# Download image zip
if ! ls "${OUT_DIR}/${RASPBIAN_IMAGE}"; then
  pushd "$(mktemp -d -t aiy-download.XXXXXXXXXX)"
  curl -O "${RASPBIAN_IMAGE_URL}" \
       -O "${RASPBIAN_IMAGE_URL}.sha256"
  if "${SHA256SUM}" -c "${RASPBIAN_IMAGE}.sha256"; then
    mv "${RASPBIAN_IMAGE}" "${OUT_DIR}"
  else
    echo "Image checksum check failed" >&2
    exit 1
  fi
  popd
fi

# Extract image zip
if ls "${OUT_DIR}/aiyprojects-"*.img; then
  readonly IMAGE=$(ls "${OUT_DIR}/aiyprojects-"*.img)
else
  readonly IMAGE="${OUT_DIR}/aiyprojects-$(date +%Y-%m-%d).img"
  time unzip -p "${OUT_DIR}/${RASPBIAN_IMAGE}" > "${IMAGE}"
fi

# Build image.
"${BUILD_SCRIPTS_DIR}/build_image_${BUILD_ENGINE}.sh" "${DEB_DIR}" "${IMAGE}"

# Compress image.
xz -3 --force "${IMAGE}"
"${SHA256SUM}" "${IMAGE}.xz" > "${IMAGE}.xz.sha256"
"${MD5SUM}" "${IMAGE}.xz" > "${IMAGE}.xz.md5"
