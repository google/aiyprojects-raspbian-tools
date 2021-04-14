# AIY Images

## Overview

This repository contains files and scripts for building the AIY SD card images.
These images are automatically built with [Kokoro], although they can be built
manually. There are two build types and the only difference between them is
where to get `aiy-vision-firmware` and `aiy-models` Debian packages:

1.  **Release**: these packages are already prebuilt and saved at [Kokoro x20].
    TODO: should be taken from MPM package build with [Rapid].

2.  **Continuous**: these packages are built every time using `blaze`.

## Local builds

There are two ways to build an image: using Docker or without it. Docker is more
desirable and should give identical results everywhere. There are no any side
effects or permission issues (e.g. built files owned by root) on your system
with Docker build. In both cases build artifacts will go to `out` folder next to
`Makefile`. Run `make clean` to remove all of them. Some temporary build files
still will be in `packages` folder.

**Without Docker**

Run `make release` or `make continuous` for corresponding build types. It works
only on Google Linux Desktops because `prodaccess` and `blaze` are required.
Check `scripts/Dockerfile` for the software you need to install locally.

**With Docker**

1.  Install Docker

    Follow go/installdocker for Google Linux Dekstop or Laptop. Follow
    https://docs.docker.com/install/ for Macbook.

2.  Build and install Docker image

    ```
    make docker-image
    ```

After this preparation run `make docker-release` or `make docker-continuous` for
corresponding build types.

**Builds on laptop**

You can override [Kokoro x20] directory by setting `DATA_DIR` environment
variable. This is useful for the local **release** build on Google laptop:

```
DATA_DIR=${HOME}/Downloads/x20 make release
```

or

```
DATA_DIR=${HOME}/Downloads/x20 make docker-release
```

Usually you need to copy 2 files from [Kokoro x20] to your `${DATA_DIR}`:

*   2019-09-26-raspbian-buster.zip
*   aiy-models_1.0-0_all.deb
*   aiy-vision-firmware_1.1-0_all.deb

If you are building without Docker on Linux laptop, probably you need to run

```
sudo ufw disable
```

to allow networking within `chroot`.

## Flash and test

Build image locally or get the image from the latest Kokoro green job by
following Placer or x20 link. Insert an SD card into your computer and write the
image:

```
xzcat path/to/aiyprojects-YYYY-MM-DD.xz | \
    sudo dd of=<SD card device, e.g. /dev/mmcblk0> bs=4M status=progress
```

## Release

Publish the image to [Placer]:

```
# Initial setup for knowledge-flex-pool (just for the record)
alias placer=/google/data/ro/projects/placer/placer
placer setup_delegation /placer/prod spacepark
placer update_alloc /placer/prod spacepark:voice --replicas=cb-d,lg-d,lh-d,ya-d
placer update_config --user=spacepark --group=spacepark --alloc=spacepark:voice /placer/prod/home/spacepark/voice
fileutil --gfs_user=spacepark mkdir /placer/prod/scratch/home/spacepark/voice/

# Release an image
IMAGE=aiyprojects-$(date +%Y-%m-%d).img.xz
placer prepare /placer/prod/scratch/home/spacepark/voice/${IMAGE}
fileutil --gfs_user=spacepark cp ${IMAGE} /placer/prod/scratch/home/spacepark/voice/
placer publish /placer/prod/scratch/home/spacepark/voice/${IMAGE}

# Verify
placer list_replicas /placer/prod/home/spacepark/voice/${IMAGE}
```

To continue, you will need to be in the [lorry-aiyprojects] MDB group. Clone the
file and the redirect in [AIY Lorry Downloads]. Add the placer path into the
perforce path field and leave the CL field empty. Next ping someone from the
team to approve the download.

Make sure that the redirect is not approved before the new file is live -- it
can take around 40-50 minutes to upload. Once the new downloads are live, revoke
the old ones.
