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

import os
import sys
import shutil
import re
import threading
import subprocess
import time
import logging

log_format = "[%(asctime)s-%(pathname)s-%(levelname)s] %(message)s"

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
formatter = logging.Formatter(log_format)
ch.setFormatter(formatter)
logger.addHandler(ch)

FIRMWARE_PATH = "/lib/firmware"
HAT_PRODUCT_NAME_PATH = "/sys/firmware/devicetree/base/hat/product"
HAT_PRODUCT_VERSION_PATH = "/sys/firmware/devicetree/base/hat/product_ver"

AIY_IO_STATUS_MESSAGE_PATH = "/sys/bus/i2c/devices/1-00%2X/status_message"
AIY_IO_UPDATE_FIRMWARE_PATH = "/sys/bus/i2c/devices/1-00%2X/update_firmware"

VISIONBONNET_PRODUCT = r"AIY VisionBonnet"
VOICEBONNET_PROUDCT = r"AIY VoiceBonnet"

FIRMWARE_PATH_DICT = {
    (VISIONBONNET_PRODUCT, "0x0001"): ("aiy_mcu_fw_vision_pvt_0.5.bin", "0.5"),
    (VISIONBONNET_PRODUCT, "0x0002"): ("aiy_mcu_fw_vision_pvt2_0.5.bin", "0.5"),
    (VOICEBONNET_PROUDCT, "0x0001"): ("aiy_mcu_fw_voice_pvt_0.5.bin", "0.5")
}

MCU_I2C_ADDRESS_DICT = {
    VISIONBONNET_PRODUCT: 0x51,
    VOICEBONNET_PROUDCT: 0x52
}


def get_product_name():
    if not os.path.exists(HAT_PRODUCT_NAME_PATH):
        logger.error(
            "Hat overlay not loaded. MCU never flashed? Board connected?")
        sys.exit(1)
    with open(HAT_PRODUCT_NAME_PATH, "r") as f:
        hat_product_name = str(f.read()).strip("\x00").strip()
    return hat_product_name


def get_product_version():
    if not os.path.exists(HAT_PRODUCT_VERSION_PATH):
        logger.error("Hat overlay version not found.")
        sys.exit(1)
    with open(HAT_PRODUCT_VERSION_PATH, "r") as f:
        hat_product_version = str(f.read()).strip("\x00").strip()
    return hat_product_version


def get_firmware_path():
    hat_product_id = (get_product_name(), get_product_version())
    logger.info(" Retrieved product name %s, version %s", *hat_product_id)
    firmware_path = FIRMWARE_PATH_DICT.get(hat_product_id, None)
    if not firmware_path:
        logger.error("Product id not found %s", hat_product_id)
        sys.exit(1)
    return firmware_path


def get_i2c_address():
    mcu_i2c_address = MCU_I2C_ADDRESS_DICT.get(get_product_name())
    if mcu_i2c_address is None:
        logger.error("Failed to determine mcu i2c address.")
        sys.exit(1)
    return mcu_i2c_address


def get_status_message():
    if not os.path.exists(AIY_IO_STATUS_MESSAGE_PATH % get_i2c_address()):
        logger.error("Status message not available, is the module loaded?")
        sys.exit(1)
    with open(AIY_IO_STATUS_MESSAGE_PATH % get_i2c_address(), "r") as status_file:
        status_message = status_file.read()
        logger.info("Status - %s", status_message)
        return status_message


def get_version_string(status_message):
    mat = re.match("^OK-V(?P<version>\d.\d)", status_message)
    if not mat:
        logger.error("Failed to find version string instead %s.",
                     status_message)
        return None
    version_string = mat.groupdict()['version']
    logger.info("Version found %s", version_string)
    return version_string


def needs_update(status_message, new_version):
    version_string = get_version_string(status_message)
    update = version_string != new_version
    if not update:
        logger.info("Hat versions match %s == %s", new_version, version_string)
    else:
        logger.info("Hat needs updating %s != %s", new_version, version_string)
    return update


def update_mcu(firmware_path):
    full_firmware_path = os.path.join(FIRMWARE_PATH, firmware_path)
    logger.info("Flashing with %s", full_firmware_path)
    if not os.path.exists(full_firmware_path):
        logger.error("Failed to find firmware %s", full_firmware_path)
        sys.exit(1)

    with open(AIY_IO_UPDATE_FIRMWARE_PATH % get_i2c_address(), "w") as update_path:
        update_path.write(firmware_path)

    logger.info("Update was successful")


def main():
    status_message = get_status_message()
    firmware_path, firmware_version = get_firmware_path()
    flash_status = needs_update(status_message, firmware_version)
    if flash_status:
        update_mcu(firmware_path)
    else:
        logger.info("MCU firmware version correct")
        sys.exit(0)
    status_message = get_status_message()
    flash_status = needs_update(status_message, firmware_version)
    if flash_status:
        logger.error("After flashing mcu firmware"
                     " version still invalid,"
                     " update firmware %s", firmware_path)
        sys.exit(1)

    logger.info("Flashing MCU a success, reboot required ...")


if __name__ == "__main__":
    main()
