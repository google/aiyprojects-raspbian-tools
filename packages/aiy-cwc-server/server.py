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
To run server (set PYTHONASYNCIODEBUG for better debug output):

    PYTHONASYNCIODEBUG=1 ./server.py

To monitor and resolve service on Linux host:

    avahi-browse -r _aiy_cwc._tcp

To monitor services on macOS:

    dns-sd -B _aiy_cwc._tcp
"""

import aiohttp
import argparse
import asyncio
import base64
import collections
import concurrent.futures
import contextlib
import logging
import os
import subprocess
import sys
import tempfile
import time
import weakref

try:
    import simplejson as json
except ImportError:
    import json

from aiohttp import web
from functools import partial

import schema

logger = logging.getLogger(__name__)

def track_websockets(app):
    async def close_all(application):
        for ws in set(application['websockets']):
            await ws.close(code=aiohttp.WSCloseCode.GOING_AWAY,
                           message='Server shutdown.')

    app['websockets'] = weakref.WeakSet()
    app.on_shutdown.append(close_all)

@contextlib.contextmanager
def register_websocket(app, ws):
    try:
        app['websockets'].add(ws)
        yield
    finally:
        app['websockets'].discard(ws)

@contextlib.contextmanager
def TempDirectory(files):
    with tempfile.TemporaryDirectory(prefix='aiy-') as d:
        for name, code in files.items():
            with open(os.path.join(d, name), 'wb') as f:
                f.write(code.encode('utf-8'))
                f.flush()
        yield d

@contextlib.contextmanager
def LogWarning(message='%s'):
    try:
        yield
    except Exception as e:
        logger.warning(message, e)

CONVERT = {
    'pipe': asyncio.subprocess.PIPE,
    'stdout': asyncio.subprocess.STDOUT,
    'null': asyncio.subprocess.DEVNULL
}

async def start_process(args, stdout, stderr, env, cwd):
    logger.info('Starting process: %s.', args)
    process = await asyncio.create_subprocess_exec(*args,
                                    stdin=asyncio.subprocess.PIPE,
                                    stdout=CONVERT[stdout],
                                    stderr=CONVERT[stderr],
                                    env=collections.ChainMap(env, os.environ),
                                    cwd=cwd)
    logger.info('Process (pid=%d) has been started.', process.pid)
    return process

async def wait_process(process, wait_op):
    if wait_op.done():
        code = wait_op.result()
    else:
        logger.info('Killing process (pid=%d).', process.pid)
        try:
            process.kill()
        except ProcessLookupError:
            pass
        code = await wait_op
    logger.info('Process (pid=%d) finished with code %d.', process.pid, code)
    return code

def signal_process(process, signum):
    logger.info('Sending signal %d to process (pid=%d).', signum, process.pid)
    process.send_signal(signum)

def stream_msg(data, kind):
    return {'type': kind,
            'data': base64.b64encode(data).decode('utf-8')}

def exit_msg(code):
    return {'type': 'exit',
            'code': code}

def validate_msg(msg):
    return msg  # No validation by default.

def parse_run_msg(msg):
    if validate_msg(msg).get('type') != 'run':
        return None
    return msg['args'], \
           msg.get('chunk_size', 1024), \
           msg.get('stdout', 'pipe'), \
           msg.get('stderr', 'pipe'), \
           msg.get('env', {}), \
           msg.get('files', {})

def parse_signal_msg(msg):
    if validate_msg(msg).get('type') != 'signal':
        return None
    return msg['signum'],

def parse_stdin_msg(msg):
    if validate_msg(msg).get('type') != 'stdin':
        return None
    return base64.b64decode(msg['data'].encode('utf-8')),

async def ReadOp(stream, kind, chunk_size, ws):
    while True:
        data = await stream.read(chunk_size)
        if not data:
            break
        await ws.send_json(stream_msg(data, kind))

async def ReceiveOp(process, ws):
    async for msg in ws:
        with LogWarning():
            if msg.type == aiohttp.WSMsgType.TEXT:
                parsed = json.loads(msg.data)

                signal_msg = parse_signal_msg(parsed)
                if signal_msg:
                    signum, = signal_msg
                    signal_process(process, signum)

                stdin_msg = parse_stdin_msg(parsed)
                if stdin_msg:
                    data, = stdin_msg
                    if data:
                        process.stdin.write(data)
                    else:
                        process.stdin.close()

async def communicate(ws):
    run_msg = parse_run_msg(await ws.receive_json())
    if not run_msg:
        return

    args, chunk_size, stdout, stderr, env, files = run_msg
    with TempDirectory(files) as cwd:
        process = await start_process(args, stdout, stderr, env, cwd)
        receive_op = asyncio.ensure_future(ReceiveOp(process, ws))
        wait_op = asyncio.ensure_future(process.wait())
        try:
            operations = [wait_op]
            if process.stdout:
                operations.append(ReadOp(process.stdout, 'stdout', chunk_size, ws))
            if process.stderr:
                operations.append(ReadOp(process.stderr, 'stderr', chunk_size, ws))
            await asyncio.wait(operations)
        except concurrent.futures.CancelledError:
            pass
        receive_op.cancel()
        code = await wait_process(process, wait_op)
        await ws.send_json(exit_msg(code))

async def spawn(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logger.info('Client (id=%s) connected.', id(ws))

    with register_websocket(request.app, ws):
        with LogWarning('Client (id=%s) communication problem: %%s' % id(ws)):
            await communicate(ws)

    logger.info('Client (id=%s) disconnected.', id(ws))
    return ws

async def publish_service(app, name, port):
    cmd = ['avahi-publish-service', name, '_aiy_cwc._tcp', str(port), 'CWC Server']
    app['publisher'] = subprocess.Popen(cmd, shell=False)

async def unpublish_service(app):
    app['publisher'].terminate()
    app['publisher'].wait()

def enable_validation():
    global validate_msg

    with LogWarning('jsonschema is not installed, skipping validation.'):
        import jsonschema
        def validate_msg(msg):
            jsonschema.validate(msg, schema.SERVER_COMMANDS)
            return msg

def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--mdns_name', default='')
    parser.add_argument('--validate', action='store_true', default=False)
    args = parser.parse_args()

    if args.validate:
        enable_validation()

    app = web.Application()
    track_websockets(app)
    if args.mdns_name:
        app.on_startup.append(partial(publish_service, name=args.mdns_name, port=args.port))
        app.on_cleanup.append(unpublish_service)
    app.add_routes([web.get('/spawn', spawn)])
    web.run_app(app, host=args.host, port=args.port)

if __name__ == '__main__':
    main()
