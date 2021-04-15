# AIY Projects Tools

This repository contains scripts to build an SD card image for [AIY Vision Kit][aiy-vision]
and [AIY Voice Kit][aiy-voice].

## Build Instructions

To build an AIY SD card image inside the docker container on Linux or Mac:

```
make docker-release
```

To build an AIY SD card image directly on Linux:

```
make release
```

Get the produced SD card image from `out` directory.

## Releases

You can find released SD card images at https://github.com/google/aiyprojects-raspbian/releases.

[aiy-vision]: https://aiyprojects.withgoogle.com/vision/
[aiy-voice]: https://aiyprojects.withgoogle.com/voice/

