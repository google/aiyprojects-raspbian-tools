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
Tools for working with images of SD cards, in particular for the Raspberry Pi.
"""

import collections
from contextlib import contextmanager
import re
import subprocess
import sys
import tempfile

SECTOR_BYTES = 512

@contextmanager
def LoopDev(args, image, offset=0):
  '''Creates a loopback device for a file.
  args: args struct with verbosity settings
  image: path to image
  offset: offset in image to skip (in bytes)
  '''

  output = subprocess.check_output(
      ['sudo', 'losetup', '-f', '--show', '-o', str(offset), image],
      stderr=subprocess.STDOUT).decode('utf-8')
  dev = output.strip()

  try:
    yield dev
  finally:
    subprocess.check_call(['sudo', 'losetup', '-d', dev],
                          stdout=args.stdout, stderr=args.stderr)

@contextmanager
def MountAt(args, image, mountpoint, offset=0):
  '''Mounts a loopback device for a file at a given path.
  args: args struct with verbosity settings
  image: path to image
  mountpoint: path to mountpoint
  offset: offset in image to skip (in bytes)
  '''

  with LoopDev(args, image, offset) as loop_dev:
    subprocess.check_call(['sudo', 'mount', loop_dev, mountpoint],
                          stdout=args.stdout, stderr=args.stderr)

    try:
      yield mountpoint
    finally:
      subprocess.check_call(['sudo', 'umount', mountpoint],
                            stdout=args.stdout, stderr=args.stderr)

@contextmanager
def Mount(args, image, offset=0):
  '''Mounts a loopback device for a file, creating a temporary mountpoint.
  args: args struct with verbosity settings
  image: path to image
  offset: offset in image to skip (in bytes)
  '''

  with tempfile.TemporaryDirectory() as mountpoint:
    with MountAt(args, image, mountpoint, offset):
      yield mountpoint

@contextmanager
def BindMount(args, olddir, newdir):
  '''Remounts a directory in another place.
  args: args struct with verbosity settings
  olddir: existing directory
  newdir: mountpoint for bind mount
  '''

  subprocess.check_call(['sudo', 'mount', '--bind', olddir, newdir],
                        stdout=args.stdout, stderr=args.stderr)

  try:
    yield newdir
  finally:
    subprocess.check_call(['sudo', 'umount', newdir],
                          stdout=args.stdout, stderr=args.stderr)

PartitionInfo = collections.namedtuple(
    'PartitionInfo', ['number', 'start', 'end', 'size', 'part_type', 'fs'])

def get_partition_info(args, disk_dev):
  '''Get the info of the given partition.
  args: args struct with verbosity settings
  disk_dev: /dev path for the disk

  Returns:
    1-based dictionary of PartitionInfo instances
  '''

  parted_out = subprocess.check_output(
      ['sudo', 'parted', '-s', disk_dev, 'unit', 's', 'print'],
      stderr=subprocess.STDOUT).decode('utf-8')
  if args.verbose:
    sys.stdout.write(parted_out)

  info = {}

  for line in parted_out.splitlines():
    fields = line.strip().split()

    if len(fields) < 6:
      continue

    number, start, end, size, part_type, fs = fields[:6]

    try:
      number = int(number)
      start = int(start.strip('s'))
      end = int(end.strip('s'))
      size = int(size.strip('s'))
    except ValueError:
      continue

    info[number] = PartitionInfo(number, start, end, size, part_type, fs)

  return info

def read_partition_info(args, image_file):
  with LoopDev(args, image_file) as disk_dev:
    return get_partition_info(args, disk_dev)

def resize2fs(args, ext_dev, size='minimum'):
  '''Resize an ext2/3/4 filesystem.
  args: args struct with verbosity settings
  ext_dev: /dev path for the ext partition
  size: 'maximum' or 'minimum'

  Returns:
    new size in bytes
  '''

  subprocess.check_call(['sudo', 'e2fsck', '-yf', ext_dev],
                        stdout=args.stdout, stderr=args.stderr)

  if size == 'minimum':
    cmd = ['sudo', 'resize2fs', '-M', ext_dev]
  elif size == 'maximum':
    cmd = ['sudo', 'resize2fs', ext_dev]
  else:
    raise ValueError('size must be "minimum" or "maximum", not %r' % size)

  resize_out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8')
  if args.verbose:
    sys.stdout.write(resize_out)

  m = re.search(r'to (\d+) \(4k\) blocks', resize_out)
  if m is None:
    m = re.search(r'already (\d+) \(4k\) blocks', resize_out)
  if m is None:
    print("Couldn't determine new size from resize2fs output:\n" + resize_out, file=sys.stderr)
    sys.exit(1)

  return int(m.group(1)) * 4096

def resize_part(args, disk_dev, partition_number, new_start_sector, new_end_sector):
  '''Resize the given partition without changing its contents.
  args: args struct with verbosity settings
  disk_dev: /dev path for the disk
  partition_number: number of partition, 1-based
  new_start_sector: sector number of the new start
  new_end_sector: sector number of the new end
  '''
  commands = '\n'.join([
      # delete old partition
      'd', str(partition_number),
      # recreate with new size
      'n', 'p', str(partition_number), str(new_start_sector), str(new_end_sector),
      # write table to disk and exit
      'w',
  ]) + '\n'
  p = subprocess.Popen(['sudo', 'fdisk', disk_dev], stdin=subprocess.PIPE,
                       stdout=args.stdout, stderr=args.stderr)
  p.communicate(input=commands.encode('utf-8'))
  # ignore code, as fdisk returns 1 even when it works
