<p align="center">
  <a href="https://github.com/SirCryptic">
    <img src="https://github.com/user-attachments/assets/709c3032-fe70-4b94-86ab-959c049bd316" alt="ADBSploit" width="500" 
    onmouseover="this.style.transform='scale(1.05)'; this.style.opacity='0.8';" 
    onmouseout="this.style.transform='scale(1)'; this.style.opacity='1';">
  </a>
  
  <p align="center">
  <a href="https://github.com/sircryptic/ADBSploit/stargazers"><img src="https://img.shields.io/github/stars/sircryptic/ADBSploit.svg" alt="GitHub stars"></a>
  <a href="https://github.com/sircryptic/ADBSploit/network"><img src="https://img.shields.io/github/forks/sircryptic/ADBSploit.svg" alt="GitHub forks"></a>
  <a href="https://github.com/sircryptic/ADBSploit/watchers"><img src="https://img.shields.io/github/watchers/sircryptic/ADBSploit.svg" alt="GitHub watchers"></a>
      <br>
    <a href="https://github.com/SirCryptic/ADBSploit/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License"></a>
</p>
<h1 align="center">Preview</h1>

<center>

<details>
  <summary>Click to expand!</summary>
  
![adbsploit](https://github.com/user-attachments/assets/10a65a7c-a228-4ea0-afd3-d645a9e68dd2)
  
</details>

</center>

## Features
- Connect via IP or USB, list devices, open shell, reboot (normal/recovery/bootloader)
- Apps: install/uninstall APKs, run by package name
- Media: capture screenshots, record video/audio, mirror screen (scrcpy), open camera, get GPS
- Files: push to device, pull from device
- Fastboot: list devices, reboot modes, flash partitions, get variables, OEM unlock
- Extras: enable Wi-Fi ADB, send key events, run custom commands, view logs

## Install
- Pre-built: Download release, extract folder, run `adbsploit.exe`
- Source:
```
git clone https://github.com/SirCryptic/ADBSploit
```
```
cd ADBSploit
```
```
pip install PyQt6 patoolib pyinstaller
```
```
python adbsploit.py
```
- if you want to compile it
```
pyinstaller --onedir --icon=app_icon.ico --noconsole --add-data "app_icon.ico;." --add-data "platform-tools;platform-tools" --add-data "scrcpy;scrcpy" --hidden-import=PyQt6 --hidden-import=patoolib --exclude-module PyQt6.QtWebEngine adbsploit.py
```
## Usage
- Enable USB Debugging on device
- Connect via USB or enter IP in Connect tab
- Run `adbsploit.exe`, select device from dropdown, use tabs for features

## Notes
- USB: Detects devices via `adb devices`; select from dropdown
- IP: Use Connect tab for Wi-Fi devices
- Requires `platform-tools/adb.exe` for ADB commands
- Requires `scrcpy/scrcpy.exe` (with deps) for mirroring
- Uses `--onedir` for faster startup

---
⭐ SirCryptic

⚠️ Please use responsibly, intended for ethical testing and management only ( i will not be held responsible for misuse )
