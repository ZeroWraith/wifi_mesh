# Building Batman-Adv for Jetson

Building the batman_adv kernel module from source for NVIDIA Jetson Tegra kernels.

> [Home](Home.md) > Jetson Build

## Why Build From Source?

The Jetson's Tegra kernel does not include batman-adv by default. You must build it from source to use the mesh network.

## Prerequisites

```bash
sudo apt-get install -y build-essential git
```

You also need kernel headers. On Jetson:

```bash
# Check if headers are installed
ls /usr/src/linux-headers-$(uname -r)

# If not installed:
sudo apt-get install -y linux-headers-$(uname -r)
```

## Build Steps

### 1. Clone Source

```bash
cd /tmp
git clone https://git.open-mesh.org/batman-adv.git
cd batman-adv
```

### 2. Generate Compatibility Header

```bash
bash gen-compat-autoconf.sh
```

### 3. Build Module

```bash
sudo make -C /lib/modules/$(uname -r)/build M=/tmp/batman-adv PWD=/tmp/batman-adv modules
```

### 4. Check for Build Success

```bash
ls net/batman-adv/batman-adv.ko
```

If the file exists, the build succeeded.

### 5. Install Module

```bash
sudo make -C /lib/modules/$(uname -r)/build M=/tmp/batman-adv PWD=/tmp/batman-adv modules_install
```

### 6. Update Module Dependencies

```bash
sudo depmod -a
```

### 7. Test Load

```bash
sudo modprobe batman_adv
lsmod | grep batman
```

### 8. Make Persistent Across Reboots

```bash
echo 'batman_adv' | sudo tee /etc/modules-load.d/batman-adv.conf
```

## Using the Build Script

The project includes `build_batman_adv.sh` which automates these steps:

```bash
sudo ./build_batman_adv.sh
```

**What it does:**
1. Verifies kernel source exists
2. Enables batman_adv in kernel config (`.config`)
3. Runs `make olddefconfig`
4. Builds the batman-adv module
5. Installs to `/lib/modules/`
6. Runs `depmod -a`
7. Tests module load

## Known Issues

### timer_shutdown_sync Error

If you see:

```
error: static declaration of 'timer_shutdown_sync' follows non-static declaration
```

**Fix:** Edit `compat-include/linux/timer.h` in the batman-adv source:

Change the version check to:

```c
#if LINUX_VERSION_IS_LESS(5, 15, 148)
```

Then rebuild.

### Kernel Source Not Found

The build script looks for kernel source at a specific path. If your Jetson has a different path, update `KERNEL_SRC` in `build_batman_adv.sh`:

```bash
KERNEL_SRC="/usr/src/linux-headers-$(uname -r)"
```

### Missing Symbols

If modprobe fails with "Unknown symbol" errors, ensure the dependent modules are loaded:

```bash
sudo modprobe cfg80211
sudo modprobe mac80211
sudo modprobe batman_adv
```

## Alternative: Use Pre-Built Package

Some Jetson images include batman-adv in `linux-modules-extra`:

```bash
sudo apt-get install -y linux-modules-extra-$(uname -r)
sudo modprobe batman_adv
```

Check if this works before building from source.

## Verify Installation

After building and loading:

```bash
# Module loaded?
lsmod | grep batman

# Module info?
modinfo batman_adv

# Test creating interface?
sudo batctl if
```
