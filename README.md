# CamINmonetor 🎥🔊

A lightweight, modern, and interactive Camera and Audio Preview Monitor built using Python, PyQt5, OpenCV, and PyAudio. It is designed to act as a sleek video/audio input visualizer with seamless full-screen toggle, hover-to-reveal controls, and custom window drag-and-resize capabilities.

---

## Features

- **Live Video Streaming**: Capture feed from connected camera devices dynamically.
- **Live Audio Visualizer**: Audio input amplitude indicator meter with active output loopback playback.
- **Bezel-Free Fullscreen Mode**: Toggle borderless fullscreen using `F` or `F11`. The control bar automatically hides to give a clean screen look.
- **Hover-to-Reveal Control Bar**: Move your mouse to the bottom edge of the fullscreen view to temporarily show controls, which hide again when the mouse moves away.
- **Custom Drag-and-Resize**: Drag any window border or corner to resize the window content layout.
- **Smart Device Filtering**:
  - Automatically filters out internal microphones/loopbacks, showing only external devices (like USB mics/soundcards).
  - Dynamically queries sample rates for external devices to prevent rate mismatches.
- **Keyboard Shortcuts**: Full keyboard control without clicking.

---

## Keyboard Shortcuts

| Shortcut | Action |
| --- | --- |
| `F` or `F11` | Toggle Fullscreen |
| `Esc` | Exit Fullscreen |
| `=` or `+` | Volume Up |
| `-` or `_` | Volume Down |
| `M` | Mute / Unmute |
| `1` - `9` | Select Video Source (Camera Index 1-9) |

---

## Prerequisites

Ensure you have Python 3 and the necessary system audio headers installed.

### On Debian/Ubuntu/Kali Linux:
```bash
sudo apt update
sudo apt install python3-pip python3-pyqt5 python3-pyaudio portaudio19-dev python3-opencv
```

---

## Installation

You can install this application as a desktop launcher shortcut in two ways:

### 1. Local User-Space Installation (No root/sudo required)
Installs only for the current user. Creates a command wrapper under `~/.local/bin/camINmonetor` and a shortcut launcher under `~/.local/share/applications/`:
```bash
python3 install.py
```

### 2. System-Wide Installation (Requires sudo)
Installs globally under `/opt/camINmonetor/`, creates a command wrapper under `/usr/local/bin/camINmonetor`, and a global shortcut under `/usr/share/applications/`:
```bash
sudo python3 install.py
```

---

## Running the Application

After running the installer:
- **Applications Menu**: Open your desktop application menu (press `Super`/`Windows` key) and search for **CamINmonetor**.
- **Terminal Launcher**: Open a terminal and run:
  ```bash
  camINmonetor
  ```
- **Direct Run (Without installing)**:
  ```bash
  python3 cam_preview.py
  ```
