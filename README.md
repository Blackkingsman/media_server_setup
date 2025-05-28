# Media Server Setup Script

This script automates the setup of a personal media server environment on **Linux** systems.

## Features

- Automated Docker and NVIDIA GPU setup
- Storage pool creation using mergerfs (no RAID, just max storage)
- Media directories and Docker containers for Radarr, Sonarr, Jellyfin, Tdarr, SABnzbd, Portainer, Watchtower, and more
- PIA (Private Internet Access) VPN integration

## Requirements

- Linux (tested on Linux Mint)
- Intel CPU (tested)
- NVIDIA GPU (tested with 1070 Ti)
- sudo privileges

## Usage

1. **Clone this repository:**
    ```sh
    git clone git@github.com:Blackkingsman/media_server_setup.git
    cd media_server_setup
    ```

2. **Run the script:**
    ```sh
    python3 install_server.py
    ```

3. **Follow the prompts.**
    - If you enable GPU acceleration and the NVIDIA driver is not installed, the script will install it and require a reboot.
    - On rerun, it will detect the driver and skip installation if already present.

## Notes

- This script is intended for Linux systems only.
- Many features may not work or may break on other OSes.
- If you have a similar setup (Linux, NVIDIA GPU), this script should work for you.
- Use at your own risk!

## PIA VPN Installers

PIA VPN installers for Linux, macOS, and Windows are available on the [Releases page](https://github.com/Blackkingsman/media_server_setup/releases).

---

## License

MIT License

Copyright (c) 2025 Terry Phillips

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
