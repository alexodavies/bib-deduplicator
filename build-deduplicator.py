#!/usr/bin/env python3
"""
Simple build script for BibTeX Deduplicator
Run this to create the desktop app automatically
"""

import os
import sys
import subprocess
import shutil
import platform

def clean_build():
    """Clean previous build files"""
    for folder in ['dist', 'build', '__pycache__']:
        if os.path.exists(folder):
            print(f"Cleaning {folder}...")
            shutil.rmtree(folder)
    
    # Remove .spec file
    spec_file = 'BibTeX-Deduplicator.spec'
    if os.path.exists(spec_file):
        os.remove(spec_file)

def install_pyinstaller():
    """Install PyInstaller if not present"""
    try:
        import PyInstaller
        print("✅ PyInstaller already installed")
    except ImportError:
        print("📦 Installing PyInstaller...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'], check=True)
        print("✅ PyInstaller installed")

def build_app():
    """Build the application"""
    print("🔨 Building BibTeX Deduplicator...")
    
    # Base command
    cmd = [
        'pyinstaller',
        '--onefile',
        '--windowed',
        '--name', 'BibTeX-Deduplicator',
        '--clean',
        'bib_deduplicator.py'
    ]
    
    # Add icon if it exists
    icon_files = ['icon.ico', 'icon.icns', 'icon.png']
    for icon in icon_files:
        if os.path.exists(icon):
            cmd.extend(['--icon', icon])
            print(f"📎 Using icon: {icon}")
            break
    
    # Platform-specific adjustments
    if platform.system() == 'Darwin':  # macOS
        cmd.extend(['--osx-bundle-identifier', 'com.bibtex.deduplicator'])
    
    print(f"Command: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed: {e}")
        return False

def show_results():
    """Show build results"""
    system = platform.system()
    if system == 'Windows':
        exe_name = 'BibTeX-Deduplicator.exe'
    else:
        exe_name = 'BibTeX-Deduplicator'
    
    exe_path = os.path.join('dist', exe_name)
    
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\n🎉 Build successful!")
        print(f"📁 Location: {exe_path}")
        print(f"📏 Size: {size_mb:.1f} MB")
        print(f"\n💡 You can now distribute this single file to users")
        print(f"   They can double-click it to run without installing Python!")
    else:
        print(f"❌ Build failed - executable not found at {exe_path}")

def main():
    """Main build process"""
    print("🚀 BibTeX Deduplicator Build Script")
    print("=" * 40)
    
    # Check if source file exists
    if not os.path.exists('bib_deduplicator.py'):
        print("❌ Error: bib_deduplicator.py not found in current directory")
        return
    
    # Build process
    clean_build()
    install_pyinstaller()
    
    if build_app():
        show_results()
    else:
        print("\n❌ Build failed. Try running with --debug for more info:")
        print("   pyinstaller --onefile --name BibTeX-Deduplicator bib_deduplicator.py")

if __name__ == "__main__":
    main()