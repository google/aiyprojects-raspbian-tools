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
Common utilities for building image.
"""

import contextlib
import distutils.spawn
import os
import shutil
import subprocess
import sys

from imgtools import SECTOR_BYTES, Mount, MountAt, BindMount, LoopDev, resize2fs, resize_part, get_partition_info


def do_expand(args, image_file, expand_bytes=(2 ** 30)):
  '''Expand the root filesystem on the image.'''

  expand_sectors = expand_bytes // SECTOR_BYTES

  print('Extending the image file by %d bytes' % expand_bytes)
  with open(image_file, 'ab') as f:
    f.truncate(f.tell() + expand_bytes)

  with LoopDev(args, image_file) as disk_dev:
    partition_info = get_partition_info(args, disk_dev)
    print('Increasing the size of the root partition by %d secrors' % expand_sectors)
    root_partition = partition_info[args.root_partition_number]
    start_sector = root_partition.start
    end_sector = root_partition.end + expand_sectors
    resize_part(args, disk_dev, args.root_partition_number, start_sector, end_sector)

  print('Increasing the size of the root filesystem...')
  start_bytes = start_sector * SECTOR_BYTES
  with LoopDev(args, image_file, offset=start_bytes) as root_dev:
    new_size_bytes = resize2fs(args, root_dev, 'maximum')
    print('Resized to %.1f GB' % (new_size_bytes / (2 ** 30)))
    subprocess.check_call(['sudo', 'zerofree', root_dev],
                          stdout=args.stdout, stderr=args.stderr)
    print('Zeroed free blocks')

@contextlib.contextmanager
def SetupEmulator(args, root_mnt):
  '''Set up the QEMU emulator so it works from within the chroot.

  As described here: https://wiki.debian.org/RaspberryPi/qemu-user-static
  '''

  ld_so_preload_path = os.path.join(root_mnt, 'etc', 'ld.so.preload')
  ld_so_preload_backup = ld_so_preload_path + '.bak'
  qemu_src_path = distutils.spawn.find_executable('qemu-arm-static')
  qemu_dst_path = os.path.join(root_mnt, 'usr', 'bin', 'qemu-arm-static')

  if qemu_src_path is None:
    print('Failed to find qemu-arm-static.', file=sys.stderr)
    print('    sudo apt-get install qemu qemu-user-static binfmt-support', file=sys.stderr)
    sys.exit(1)

  # The RPi preloads an optimized memcpy, which we need to disable to use the
  # network with QEMU.
  os.rename(ld_so_preload_path, ld_so_preload_backup)

  try:
    shutil.copy(qemu_src_path, qemu_dst_path)

    try:
      yield
    finally:
      os.unlink(qemu_dst_path)

  finally:
    os.rename(ld_so_preload_backup, ld_so_preload_path)


@contextlib.contextmanager
def MountPoint(path):
  def find_existing(path):
    name = None
    while path:
      if os.path.exists(path):
        return (path, name)
      path, name = os.path.split(path)

  existing_path, name = find_existing(path)
  if name:
    os.makedirs(path)
    try:
      yield
    finally:
      shutil.rmtree(os.path.join(existing_path, name))
  else:
    yield


@contextlib.contextmanager
def MountAndSetupEmulator(args, partition_info, image_file, mounts=None):
  boot_start_bytes = partition_info[args.boot_partition_number].start * SECTOR_BYTES
  root_start_bytes = partition_info[args.root_partition_number].start * SECTOR_BYTES

  all_mounts = [('/dev', '/dev'),
                ('/sys', '/sys'),
                ('/proc', '/proc'),
                ('/dev/pts', '/dev/pts')] + (mounts or [])

  with Mount(args, image_file, offset=root_start_bytes) as root_mnt:
    with contextlib.ExitStack() as stack:
      stack.enter_context(MountAt(args, image_file, os.path.join(root_mnt, 'boot'),
                                  offset=boot_start_bytes))
      for host_path, img_path in all_mounts:
        assert os.path.exists(host_path)
        assert os.path.isabs(img_path)
        abs_img_path = os.path.join(root_mnt, img_path[1:])
        print('Bind mount: %s => %s' % (host_path, abs_img_path))
        stack.enter_context(MountPoint(abs_img_path))
        stack.enter_context(BindMount(args, host_path, abs_img_path))
      stack.enter_context(SetupEmulator(args, root_mnt))
      yield root_mnt


def run_in_chroot(args, root_mnt, cmd, env=None):
  '''Run the given command chrooted into the image.'''
  if not cmd:
    raise ValueError('cmd must not be empty')
  elif cmd[0].startswith('/') or not os.path.isfile(os.path.join(root_mnt, cmd[0])):
    raise ValueError('cmd[0] must be a relative path to a binary in the image')

  env_list = ['%s=%s' % item for item in (env or {}).items()] + [
      'LANG=C.UTF-8',  # en_US isn't installed on the default RPi image, so use C
      'LANGUAGE=C:',
      'LC_CTYPE=C.UTF-8',
      'QEMU_CPU=arm1176',  # Use armv6l for compatability with Pi Zero.
  ]

  chroot_cmd = ['sudo'] + env_list + ['chroot', '.'] + cmd
  return subprocess.call(chroot_cmd, cwd=root_mnt, stdout=args.stdout, stderr=args.stderr)
