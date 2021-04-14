# Coding with Chrome Server

## Overview

For each incoming client connection server reads python source code and executes
it locally while sending stderr/stdout messages back to the client. All clients
work concurrently without blocking each other. There is one python process per
client.

## Server

Run `server.py` on the Pi:

```
$ ./server.py
```

Run `server.py` on the Pi and enable Avahi service publishing:

```
$ ./server.py --publish VisionKit
```

To monitor available CWC services run on any Linux machine in the same network:

```
avahi-browse -r _aiy_cwc._tcp
```

## Python Client

Run `client.py` on another host connected to the Pi:
```
./client.py --host raspberrypi.local -f samples/helloworld.py
```
or
```
./client.py --host raspberrypi.local -f samples/longloop.py
```
or
```
./client.py --host raspberrypi.local -f samples/sysinfo.py
```

## Web Client

Open `client.html` in the browser.
