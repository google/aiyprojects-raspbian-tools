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

if [[ "$#" -ne 2 ]]; then
  echo "$0 <deb_dir> <image>" >&2
  exit 1
fi

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DEB_DIR="$1"
readonly IMAGE="$2"

function shell_image {
  sudo PYTHONDONTWRITEBYTECODE=yes "${SCRIPT_DIR}/shell_image.py" "$@"
}

function expand_image {
  sudo PYTHONDONTWRITEBYTECODE=yes "${SCRIPT_DIR}/expand_image.py" "$@"
}

# Resize image if needed.
if ! shell_image "${IMAGE}" "ls /tmp/resized"; then
  expand_image --expand-bytes $((500*1024*1024)) "${IMAGE}"
  shell_image "${IMAGE}" "touch /tmp/resized"
fi

# Build debian packages except
#    aiy-models_*_all.deb
#    aiy-vision-firmware_*_all.deb
"${SCRIPT_DIR}/../packages/make_dpkg.sh" "${DEB_DIR}"

# Run image setup script.
shell_image \
    --mount "${DEB_DIR}:/deb" \
    --mount "${SCRIPT_DIR}/..:/aiy" \
    --mount "${SCRIPT_DIR}/../overlay:/overlay" \
    --arg "Build info: $(LANG=C date -u) @ $(git -C "${SCRIPT_DIR}" rev-parse --short HEAD)" \
    --arg /deb \
    --arg /aiy/packages/aiy-projects-python \
    --arg /overlay \
    "${IMAGE}" < "${SCRIPT_DIR}/setup_image.sh"

# Clean /tmp.
if [[ -n "${AIY_CLEAN_TMP}" ]]; then
  shell_image "${IMAGE}" "rm -f /tmp/*"
fi
