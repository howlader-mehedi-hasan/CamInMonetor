#!/usr/bin/env python3
import os
import sys
import shutil

def main():
    # Detect if running with root privileges
    is_root = os.geteuid() == 0

    # Source files paths
    src_dir = os.path.dirname(os.path.abspath(__file__))
    src_py = os.path.join(src_dir, 'cam_preview.py')
    src_icon = os.path.join(src_dir, 'pyCamIn.jpeg')

    if not os.path.exists(src_py):
        print(f"Error: cam_preview.py not found at {src_py}")
        sys.exit(1)

    # Determine installation directories
    if is_root:
        print("Root privileges detected. Installing system-wide...")
        install_dir = "/opt/camINmonetor"
        bin_dir = "/usr/local/bin"
        desktop_dir = "/usr/share/applications"
    else:
        print("Installing for the current user only...")
        home = os.path.expanduser("~")
        install_dir = os.path.join(home, ".local/share/camINmonetor")
        bin_dir = os.path.join(home, ".local/bin")
        desktop_dir = os.path.join(home, ".local/share/applications")

    # Create target directories
    try:
        os.makedirs(install_dir, exist_ok=True)
        os.makedirs(bin_dir, exist_ok=True)
        os.makedirs(desktop_dir, exist_ok=True)
    except Exception as e:
        print(f"Error creating directories: {e}")
        print("Try running the script with 'sudo python3 install.py' for a system-wide install.")
        sys.exit(1)

    # Copy script and icon files
    dest_py = os.path.join(install_dir, 'cam_preview.py')
    dest_icon = os.path.join(install_dir, 'pyCamIn.jpeg')

    try:
        shutil.copy2(src_py, dest_py)
        if os.path.exists(src_icon):
            shutil.copy2(src_icon, dest_icon)
            print(f"Copied icon to {dest_icon}")
        else:
            print("Warning: pyCamIn.jpeg icon not found. App will use default system icon.")
    except Exception as e:
        print(f"Error copying files: {e}")
        sys.exit(1)

    # Create target executable wrapper
    wrapper_path = os.path.join(bin_dir, 'camINmonetor')
    python_exec = sys.executable  # Hardcodes the python interpreter used for installation

    wrapper_content = f"""#!/bin/bash
# Wrapper to launch camINmonetor with the correct Python interpreter
exec "{python_exec}" "{dest_py}" "$@"
"""

    try:
        with open(wrapper_path, 'w') as f:
            f.write(wrapper_content)
        os.chmod(wrapper_path, 0o755)
        print(f"Created executable wrapper at {wrapper_path}")
    except Exception as e:
        print(f"Error creating wrapper: {e}")
        sys.exit(1)

    # Create desktop shortcut launcher
    desktop_path = os.path.join(desktop_dir, 'camINmonetor.desktop')
    desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=CamINmonetor
Comment=Camera and Audio Preview Monitor
Exec={wrapper_path}
Icon={dest_icon if os.path.exists(src_icon) else 'video-x-generic'}
Terminal=false
Categories=AudioVideo;Utility;
"""

    try:
        with open(desktop_path, 'w') as f:
            f.write(desktop_content)
        os.chmod(desktop_path, 0o755)
        print(f"Created desktop shortcut launcher at {desktop_path}")
    except Exception as e:
        print(f"Error creating desktop entry: {e}")
        sys.exit(1)

    print("\nInstallation completed successfully!")
    if is_root:
        print("You can run the application by typing 'camINmonetor' in any terminal, or search for it in your applications launcher.")
    else:
        print("You can launch the application from your applications menu.")
        print(f"To run it from the terminal, ensure that {bin_dir} is in your shell's PATH variable.")

if __name__ == '__main__':
    main()
