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

import hashlib
import os
import sys

from collections import namedtuple

AIY_BOARDS = {1: 'Voice-HAT', 2: 'Vision-Bonnet', 3: 'Voice-Bonnet'}

Board = namedtuple('Board',
                   ['product', 'product_id', 'product_ver', 'uuid', 'vendor'])


def simple_hash(data, length=4):
    digest = hashlib.md5(data).digest()
    return ''.join(str(digest[i] % 10) for i in range(length))


def device_tree_node(node):
    with open(os.path.join('/proc/device-tree/', node), 'rb') as f:
        return f.read().replace(b'\x00', b'')


def board_info():
    if os.path.exists('/proc/device-tree/hat/'):
        # hat/bonnet is attached.
        board = Board(product=device_tree_node('hat/product').decode('utf-8'),
                      product_id=int(device_tree_node('hat/product_id'), 16),
                      product_ver=int(device_tree_node('hat/product_ver'), 16),
                      uuid=device_tree_node('hat/uuid'),
                      vendor=device_tree_node('hat/vendor').decode('utf-8'))
        if board.vendor == 'Google, LLC':
            board_id = board.product_id
            name = AIY_BOARDS.get(board_id, 'AIY-Board')
        else:
            board_id = 0
            name = 'Board'
        return board_id, '%s-%s' % (name, simple_hash(board.uuid))

    # hat/bonnet is not attached.
    return 0, 'Raspberry-Pi-%s' % simple_hash(device_tree_node('serial-number'))


def main():
    msg = 'AIY_BOARD_ID=%d\nAIY_BOARD_NAME=%s\n' % board_info()
    if len(sys.argv) == 2:
        with open(sys.argv[1], 'w') as f:
            f.write(msg)
    else:
        print(msg, end='')

if __name__ == '__main__':
    main()
