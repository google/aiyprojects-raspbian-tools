#!/usr/bin/env python3

# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Connect to local server:
python3 client.py samples/longloop.py -- -n 100 -p 0.01

Connect to remote server:
python3 client.py --host 192.168.11.2 samples/longloop.py -- -n 100 -p 0.01
"""

import aiohttp
import argparse
import asyncio
import base64
import fcntl
import json
import os
import random
import signal
import sys

from functools import partial

def set_nonblocking(fileno):
    fl = fcntl.fcntl(fileno, fcntl.F_GETFL)
    return fcntl.fcntl(fileno, fcntl.F_SETFL, fl | os.O_NONBLOCK)

def read_file(file):
    with open(file) as f:
        return f.read()

def encode(data):
    return base64.b64encode(data).decode('utf-8')

def decode(data):
    return base64.b64decode(data.encode('utf-8'))

def make_run_msg(args, stdout, stderr, chunk_size, env, files):
    return {'type': 'run',
            'args': args,
            'stdout': stdout,
            'stderr': stderr,
            'chunk_size': chunk_size,
            'env': env,
            'files': files}

def make_signal_msg(signum):
    return {'type': 'signal',
            'signum': signum}

def make_stdin_msg(data):
    return {'type': 'stdin',
            'data': encode(data)}

def sigint_handler(ws):
    """Ctrl-C handler."""
    asyncio.ensure_future(ws.send_json(make_signal_msg(signal.SIGINT)))

def siginfo_handler(ws):
    """Ctrl-T handler."""
    asyncio.ensure_future(ws.send_json(make_signal_msg(signal.SIGKILL)))

async def send_stdin(queue, ws):
    while True:
        data = await queue.get()
        await ws.send_json(make_stdin_msg(data))

async def run(session, uri, run_msg, handle_sigint):
    def read_stdin(queue):
        data = sys.stdin.buffer.read(100 * 1024)
        asyncio.ensure_future(queue.put(data))

    async with session.ws_connect(uri) as ws:
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        loop.add_reader(sys.stdin, partial(read_stdin, queue=queue))
        asyncio.ensure_future(send_stdin(queue, ws))

        await ws.send_json(run_msg)

        loop.add_signal_handler(signal.SIGINFO, partial(siginfo_handler, ws=ws))

        if handle_sigint:
            loop.add_signal_handler(signal.SIGINT,
                partial(sigint_handler, ws=ws))

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                params = json.loads(msg.data)
                kind = params['type']

                if kind == 'exit':
                    return params['code']
                elif kind == 'stdout':
                    sys.stdout.buffer.write(decode(params['data']))
                    sys.stdout.buffer.flush()
                elif kind == 'stderr':
                    sys.stderr.buffer.write(decode(params['data']))
                    sys.stderr.buffer.flush()

        return 127  # WebSocket was closed without sending 'exit' message.

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, default='localhost')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--chunk_size', type=int, default=1024)
    parser.add_argument('--stdout', type=str, default='pipe',
                        choices=('null', 'pipe'))
    parser.add_argument('--stderr', type=str, default='pipe',
                        choices=('null', 'pipe', 'stdout'))
    parser.add_argument('--nosigint', dest='sigint', action='store_false', default=True)
    parser.add_argument('file')
    args, unknown_args = parser.parse_known_args()

    uri = 'ws://%s:%d/spawn' % (args.host, args.port)
    code = read_file(args.file)

    async with aiohttp.ClientSession() as session:
        env = {'PYTHONUNBUFFERED': '1'}
        files = {'main.py': code}
        all_args = ['/usr/bin/env', 'python3', 'main.py'] + unknown_args
        run_msg = make_run_msg(all_args, args.stdout, args.stderr, args.chunk_size, env, files)
        return await run(session, uri, run_msg, args.sigint)

if __name__ == '__main__':
    set_nonblocking(sys.stdin.fileno())
    loop = asyncio.get_event_loop()
    code = loop.run_until_complete(main())
    sys.exit(code)
