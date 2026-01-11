# KeyHunt Smart Coordinator v3.8.0 - Installation Guide

## Table of Contents

1. [Overview](#overview)
2. [System Requirements](#system-requirements)
3. [Quick Installation](#quick-installation)
4. [Manual Installation](#manual-installation)
5. [GPU Setup](#gpu-setup)
6. [Database Backup & Restore](#database-backup--restore)
7. [Configuration](#configuration)
8. [Troubleshooting](#troubleshooting)
9. [Upgrading](#upgrading)
10. [Uninstallation](#uninstallation)

---

## Overview

KeyHunt Smart Coordinator v3.8.0 is a GTK-based GUI application that coordinates Bitcoin puzzle hunting with:

- **Pool Coordination**: Scrapes btcpuzzle.info to avoid duplicate work
- **Smart Batch Filtering**: Reduces search space by ~50-60% by filtering pattern addresses
- **Pause/Resume**: Persistent state across sessions
- **Multi-Puzzle Support**: Puzzles 71-80 with automatic database switching
- **Block Management**: Track scanned blocks, view statistics

### Components

| Component | Description |
|-----------|-------------|
| `KeyHunt` | C++ binary that performs the actual key searching |
| `keyhunt_smart_coordinator_v3.8.0.py` | Python GTK GUI coordinator |
| `backup_database.py` | Database backup/restore utility |
| `install.sh` | Automated installation script |
| `scan_data_puzzle_*.db` | SQLite databases storing scan progress |
| `keyhunt_state_puzzle_*.json` | JSON files storing session state |

---

## System Requirements

### Minimum Requirements

| Component | Requirement |
|-----------|-------------|
| **OS** | Ubuntu 18.04+ / Debian 10+ / Linux Mint 19+ |
| **CPU** | x86_64 with SSE3 support |
| **RAM** | 4 GB minimum, 8 GB recommended |
| **Disk** | 500 MB for software, 1+ GB for databases |
| **Display** | X11 or Wayland with GTK3 support |

### For GPU Support (Optional)

| Component | Requirement |
|-----------|-------------|
| **GPU** | NVIDIA GPU with compute capability 5.0+ |
| **Driver** | NVIDIA driver 450+ |
| **CUDA** | CUDA Toolkit 10.0+ |

### Software Dependencies

**System packages:**
- build-essential, g++-8, gcc-8
- libgmp-dev (GNU Multiple Precision library)
- libgtk-3-dev, gir1.2-gtk-3.0
- python3, python3-pip

**Python packages:**
- PyGObject >= 3.36.0
- pycairo >= 1.20.0
- requests >= 2.25.0
- beautifulsoup4 >= 4.9.0

---

## Quick Installation

### Option 1: Automated Installation (Recommended)

```bash
# Clone or copy the KeyHunt-Cuda directory to your machine
cd /path/to/KeyHunt-Cuda

# Make installer executable
chmod +x install.sh

# Run installer (CPU only)
./install.sh

# OR with GPU support
./install.sh --gpu

# OR with specific CUDA compute capability
./install.sh --gpu --ccap 86
```

The installer will:
1. Install all system dependencies via apt
2. Install Python packages via pip
3. Build KeyHunt from source
4. Create launcher scripts
5. Verify the installation

### Option 2: One-Line Install

```bash
# CPU only
curl -sSL https://raw.githubusercontent.com/your-repo/install.sh | bash

# With GPU
curl -sSL https://raw.githubusercontent.com/your-repo/install.sh | bash -s -- --gpu
```

---

## Manual Installation

If you prefer manual installation or the automated script fails:

### Step 1: Install System Dependencies

```bash
# Update package lists
sudo apt-get update

# Install build tools
sudo apt-get install -y build-essential g++-8 gcc-8 make git wget curl

# Install GMP library (required for big integer operations)
sudo apt-get install -y libgmp-dev

# Install GTK3 and dependencies
sudo apt-get install -y libgtk-3-dev libgirepository1.0-dev gir1.2-gtk-3.0 libcairo2-dev pkg-config

# Install Python 3
sudo apt-get install -y python3 python3-pip python3-venv python3-dev
```

### Step 2: Install Python Dependencies

```bash
# Upgrade pip
python3 -m pip install --upgrade pip

# Install required packages
python3 -m pip install PyGObject pycairo requests beautifulsoup4 lxml

# OR use requirements.txt
python3 -m pip install -r requirements.txt
```

### Step 3: Build KeyHunt

```bash
cd /path/to/KeyHunt-Cuda

# Clean any previous builds
make clean
rm -rf obj/

# Create object directories
mkdir -p obj/GPU obj/hash

# Build (CPU only)
make

# OR build with GPU support (replace XX with your compute capability)
make gpu=1 CCAP=XX
```

### Step 4: Verify Installation

```bash
# Test KeyHunt binary
./KeyHunt -h

# Test Python dependencies
python3 -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk; print('GTK OK')"
python3 -c "import requests; from bs4 import BeautifulSoup; print('Web scraping OK')"

# Launch coordinator
python3 keyhunt_smart_coordinator_v3.8.0.py
```

---

## GPU Setup

### Determining Your CUDA Compute Capability

| GPU Series | Compute Capability |
|------------|-------------------|
| GTX 750, 750 Ti | 50 |
| GTX 10 series (1050-1080) | 61 |
| Tesla V100 | 70 |
| RTX 20 series (2060-2080) | 75 |
| A100 | 80 |
| RTX 30 series (3060-3090) | 86 |
| RTX 40 series (4090) | 89 |

You can also detect it automatically:
```bash
nvidia-smi --query-gpu=compute_cap --format=csv,noheader
```

### Installing CUDA Toolkit

If CUDA is not installed:

```bash
# Download CUDA keyring
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2004/x86_64/cuda-keyring_1.1-1_all.deb

# Install keyring
sudo dpkg -i cuda-keyring_1.1-1_all.deb

# Update and install CUDA
sudo apt-get update
sudo apt-get install -y cuda-toolkit-12-0

# Add to PATH (add to ~/.bashrc for persistence)
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH
```

### Building with GPU Support

```bash
# Example for RTX 3080 (compute capability 86)
make clean
make gpu=1 CCAP=86

# Verify GPU build
./KeyHunt -h  # Should show GPU options
```

---

## Database Backup & Restore

### Understanding the Data Files

KeyHunt stores data in two types of files per puzzle:

1. **SQLite Database** (`scan_data_puzzle_XX.db`)
   - `pool_scanned`: Blocks scanned by the pool (from btcpuzzle.info)
   - `my_scanned`: Blocks you have personally scanned

2. **State File** (`keyhunt_state_puzzle_XX.json`)
   - Current block index
   - Range configuration
   - Session timestamp

### Creating a Backup

```bash
# Create a full backup (databases + state files)
python3 backup_database.py

# Create a named backup
python3 backup_database.py --name pre_upgrade_backup

# Export to SQL format (for manual inspection/editing)
python3 backup_database.py --export-sql
```

Backups are saved to the `backups/` directory as `.tar.gz` archives.

### Restoring a Backup

```bash
# List available backups
python3 backup_database.py --list

# Restore from backup
python3 backup_database.py --restore keyhunt_backup_20260111_120000.tar.gz

# Restore from specific path
python3 backup_database.py --restore /path/to/backup.tar.gz
```

### Transferring to a New Machine

1. **On the source machine:**
```bash
# Create backup
python3 backup_database.py --name transfer_backup

# The backup will be in backups/transfer_backup.tar.gz
```

2. **Transfer the backup file:**
```bash
# Using scp
scp backups/transfer_backup.tar.gz user@newmachine:/path/to/KeyHunt-Cuda/backups/
```

3. **On the new machine:**
```bash
# Run installation first
./install.sh --gpu  # or without --gpu

# Restore backup
python3 backup_database.py --restore transfer_backup.tar.gz
```

### Backup Contents Example

```
keyhunt_backup_20260111_120000.tar.gz
├── backup_metadata.json
├── scan_data_puzzle_71.db
├── scan_data_puzzle_72.db
├── keyhunt_state_puzzle_71.json
└── keyhunt_state_puzzle_72.json
```

---

## Configuration

### Puzzle Configuration

The coordinator supports puzzles 71-80. Each puzzle has:

| Puzzle | Bits | Address | Range |
|--------|------|---------|-------|
| 71 | 71 | 1NjcJAkuGn7M4BiAHF5MT2MR8xPhaHJUXi | 40000000000000000-7FFFFFFFFFFFFFFFFF |
| 72 | 72 | 1MWuSkWdEH5JtqHRSiZL5dxF3DBsRDsVXs | 80000000000000000-FFFFFFFFFFFFFFFFF |
| ... | ... | ... | ... |

### GUI Settings

In the coordinator GUI:

- **Block Size**: Number of keys per block (default: 68,719,476,736)
- **Stride**: Keys between blocks
- **Sub-range Size**: Keys per sub-range for smart filtering
- **Inter-range Delay**: Milliseconds between sub-ranges

### Command-Line Options

The KeyHunt binary supports many options:
```bash
./KeyHunt -h  # Show all options

# Common options:
#   -m MODE      Search mode (address, rmd160, etc.)
#   -t THREADS   Number of CPU threads
#   -g GPUS      GPU IDs to use (e.g., 0,1)
#   -r START:END Key range to search
#   -o FILE      Output file for found keys
```

---

## Troubleshooting

### Common Issues

#### "GTK not found" or import errors
```bash
# Reinstall PyGObject
sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0
python3 -m pip install --force-reinstall PyGObject
```

#### "g++-8 not found"
```bash
sudo apt-get install g++-8 gcc-8
# If still not found, create symlinks
sudo ln -s /usr/bin/g++-8 /usr/bin/g++
```

#### "libgmp.so not found"
```bash
sudo apt-get install libgmp-dev
# Verify
ldconfig -p | grep gmp
```

#### GPU not detected
```bash
# Check NVIDIA driver
nvidia-smi

# Check CUDA
nvcc --version

# Rebuild with correct compute capability
make clean
make gpu=1 CCAP=XX
```

#### Database locked errors
```bash
# This usually means another instance is running
pkill -f keyhunt_smart_coordinator

# Or check for zombie processes
ps aux | grep keyhunt
```

#### Permission denied on KeyHunt
```bash
chmod +x KeyHunt
```

### Checking Logs

- **Installation log**: `install.log`
- **GUI errors**: Check terminal output when running coordinator
- **KeyHunt output**: Displayed in coordinator log window

### Getting Help

1. Check the troubleshooting section above
2. Review `install.log` for installation issues
3. Run with debug output: `python3 keyhunt_smart_coordinator_v3.8.0.py 2>&1 | tee debug.log`

---

## Upgrading

### Upgrading the Coordinator

1. **Backup your data first:**
```bash
python3 backup_database.py --name pre_upgrade
```

2. **Replace the coordinator script:**
```bash
# Keep the old version
mv keyhunt_smart_coordinator_v3.8.0.py keyhunt_smart_coordinator_v3.8.0.py.old

# Copy new version
cp /path/to/new/keyhunt_smart_coordinator_vX.X.X.py .
```

3. **Verify databases are compatible (usually they are)**

### Upgrading KeyHunt Binary

```bash
# Backup current binary
cp KeyHunt KeyHunt.old

# Rebuild
make clean
make gpu=1 CCAP=XX  # or just 'make' for CPU
```

---

## Uninstallation

### Remove Software Only (Keep Data)

```bash
# Remove binaries and scripts
rm -f KeyHunt keyhunt install.log
rm -f *.pyc __pycache__/
rm -rf obj/
```

### Complete Removal (Including Data)

```bash
# WARNING: This removes all scan data!
rm -rf /path/to/KeyHunt-Cuda/

# Remove Python packages (optional)
python3 -m pip uninstall PyGObject pycairo requests beautifulsoup4
```

---

## File Reference

| File | Description |
|------|-------------|
| `KeyHunt` | Main binary (compiled) |
| `keyhunt_smart_coordinator_v3.8.0.py` | GUI coordinator |
| `backup_database.py` | Backup/restore utility |
| `install.sh` | Installation script |
| `requirements.txt` | Python dependencies |
| `start_keyhunt.sh` | Launcher script |
| `scan_data_puzzle_XX.db` | SQLite database per puzzle |
| `keyhunt_state_puzzle_XX.json` | State file per puzzle |
| `Makefile` | Build configuration |
| `*.cpp`, `*.h` | Source code |

---

## Quick Reference Card

```bash
# Install (CPU)
./install.sh

# Install (GPU)
./install.sh --gpu --ccap 86

# Start coordinator
./start_keyhunt.sh
# OR
python3 keyhunt_smart_coordinator_v3.8.0.py

# Create backup
python3 backup_database.py

# Restore backup
python3 backup_database.py --restore backup_file.tar.gz

# Export to SQL
python3 backup_database.py --export-sql

# Check dependencies
python3 -c "import gi, cairo, requests, bs4; print('All OK')"

# Rebuild KeyHunt
make clean && make gpu=1 CCAP=86
```

---

**Version**: 3.8.0
**Last Updated**: 2026-01-11
**Author**: KeyHunt Smart Coordinator Team
