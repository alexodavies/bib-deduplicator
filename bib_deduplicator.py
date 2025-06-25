#!/usr/bin/env python3
import subprocess
import sys
import platform
import os

def build_executable():
    """Build the BibTeX Deduplicator executable using PyInstaller."""
    
    # Base command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "BibTeX-Deduplicator",
        "bib_deduplicator.py"
    ]
    
    # Platform-specific options
    if platform.system() == "Windows":
        # For Windows, use windowed mode to hide console
        cmd.insert(-1, "--windowed")
    elif platform.system() == "Darwin":  # macOS
        # macOS specific options for better compatibility
        cmd.extend([
            "--windowed",
            "--target-arch", "universal2",  # Support both Intel and Apple Silicon
            "--osx-bundle-identifier", "com.alexdavies.bibtex-deduplicator"
        ])
    elif platform.system() == "Linux":
        # Linux doesn't need windowed mode for GUI apps
        pass
    
    # Add common options
    cmd.extend([
        "--clean",
        "--noconfirm"
    ])
    
    print(f"Building executable for {platform.system()}...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("Build successful!")
        print(result.stdout)
        
        # Set executable permissions on Unix-like systems
        if platform.system() in ["Darwin", "Linux"]:
            executable_path = os.path.join("dist", "BibTeX-Deduplicator")
            if os.path.exists(executable_path):
                os.chmod(executable_path, 0o755)
                print(f"Set executable permissions for {executable_path}")
        
    except subprocess.CalledProcessError as e:
        print(f"Build failed with error: {e}")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        sys.exit(1)

if __name__ == "__main__":
    build_executable()