#!/usr/bin/env python3
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
Run shell on Raspbian image.
"""

import argparse
import sys

from build_common import MountAndSetupEmulator, run_in_chroot
from imgtools import read_partition_info

def main():
  parser = argparse.ArgumentParser(
    description='Run shell on Raspbian image.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('--boot-partition-number', type=int, default=1,
                      help='boot partition number')
  parser.add_argument('--root-partition-number', type=int, default=2,
                      help='root partition number')
  parser.add_argument('--verbose', action='store_true',
                      help='show the output of the child processes')
  parser.add_argument('--mount', action='append', help='<host-path>:<image-path>')
  parser.add_argument('--arg', action='append', help='Script argument')
  parser.add_argument('image', help='path to disk image file ')
  parser.add_argument('command', nargs='?', default=None,
                      help='command to execute or nothing to open shell')

  args = parser.parse_args()
  args.stdout, args.stderr = None, None

  cmd = ['bin/bash']
  if args.command:
    cmd += ['-c', args.command]

  if args.arg:
    cmd += ['/dev/stdin'] + args.arg

  mounts = [tuple(mount.split(':')) for mount in (args.mount or [])]

  partition_info = read_partition_info(args, args.image)
  with MountAndSetupEmulator(args, partition_info, args.image, mounts) as root_mnt:
    print('Starting emulator at %s...' % root_mnt)
    sys.exit(run_in_chroot(args, root_mnt, cmd))

if __name__ == '__main__':
  main()
