"""
Launcher script for Davis Cup Match Graphic Generator.
Ensures dependencies (PyQt6, pycountry, Pillow) are installed,
prepares assets, and starts the application.
"""
import os
import sys
import subprocess

def ensure_dependencies():
    missing = []
    for pkg_import, pkg_pip in [("PyQt6", "PyQt6"), ("pycountry", "pycountry"), ("PIL", "Pillow")]:
        try:
            __import__(pkg_import)
        except ImportError:
            missing.append(pkg_pip)

    if missing:
        print("\n" + "=" * 65)
        print(f" [Davis Cup Studio] Installing required packages: {', '.join(missing)}...")
        print(f" Python environment: {sys.executable}")
        print("=" * 65 + "\n")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
            print("\n[SUCCESS] Dependencies installed successfully!\n")
        except Exception as err:
            print(f"\n[ERROR] Automatic pip install failed: {err}")
            print("\nPlease run this command manually in your terminal:")
            print(f'    "{sys.executable}" -m pip install {" ".join(missing)}\n')
            sys.exit(1)

def main():
    # 1. Ensure PyQt6, pycountry, Pillow exist
    ensure_dependencies()

    # 2. Launch main Davis Cup Studio app (Blank project with no preloaded images)
    import davis_cup_generator
    davis_cup_generator.main()

if __name__ == "__main__":
    main()
