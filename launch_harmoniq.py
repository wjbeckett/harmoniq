#!/usr/bin/env python3
"""
Harmoniq Development Launcher - Custom for Your Setup
Easy way to start both scheduler and web server for development/testing
"""

import os
import sys
import subprocess
import signal
import time
from pathlib import Path

def print_banner():
    """Print startup banner."""
    print("=" * 60)
    print("🎵 HARMONIQ - INTELLIGENT MUSIC LIBRARY MANAGEMENT")
    print("=" * 60)
    print("🚀 Starting development environment...")
    print("")

def check_requirements():
    """Check if required packages are installed."""
    required_packages = ['fastapi', 'uvicorn', 'schedule', 'requests', 'pyyaml']
    missing_packages = []

    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print(f"❌ Missing required packages: {', '.join(missing_packages)}")
        print("📦 Please install them with: pip install -r src/requirements.txt")
        return False

    return True

def start_services():
    """Start both scheduler and web server."""
    print("🔄 Starting Harmoniq services...")

    # Set Python path to match your structure
    src_path = Path(__file__).parent / "src"
    env = os.environ.copy()
    env['PYTHONPATH'] = str(src_path)

    # Change to src directory to match your Docker setup
    os.chdir("src")

    processes = []

    try:
        # Start scheduler
        print("📅 Starting scheduler...")
        scheduler_process = subprocess.Popen([
            sys.executable, "-m", "harmoniq.scheduler_main"
        ], env=env)
        processes.append(("Scheduler", scheduler_process))

        # Give scheduler time to start
        time.sleep(2)

        # Start web server
        print("🌐 Starting web server...")
        web_process = subprocess.Popen([
            sys.executable, "-m", "harmoniq.web.web_main"
        ], env=env)
        processes.append(("Web Server", web_process))

        # Give web server time to start
        time.sleep(3)

        print("")
        print("✅ Harmoniq started successfully!")
        print("")
        print("🌐 Web Dashboard: http://localhost:7845")
        print("📚 API Documentation: http://localhost:7845/api/docs")
        print("🔍 API Explorer: http://localhost:7845/api/redoc")
        print("")
        print("💡 Tips:")
        print("   • Press Ctrl+C to stop all services")
        print("   • Use Ctrl+Shift+T in the web UI to switch themes")
        print("   • Check logs for detailed information")
        print("   • Your config is loaded from ./config/config.yaml")
        print("")
        print("🎵 Harmoniq is now running! Enjoy your intelligent music library!")
        print("=" * 60)

        # Wait for processes
        def signal_handler(signum, frame):
            print("\n🛑 Shutting down Harmoniq...")
            for name, process in processes:
                if process.poll() is None:
                    print(f"   Stopping {name}...")
                    process.terminate()

            # Wait for graceful shutdown
            time.sleep(2)

            # Force kill if needed
            for name, process in processes:
                if process.poll() is None:
                    print(f"   Force stopping {name}...")
                    process.kill()

            print("✅ Harmoniq stopped successfully!")
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Monitor processes
        while True:
            for name, process in processes:
                if process.poll() is not None:
                    print(f"❌ {name} stopped unexpectedly!")
                    return False
            time.sleep(1)

    except Exception as e:
        print(f"❌ Failed to start services: {e}")

        # Cleanup
        for name, process in processes:
            if process.poll() is None:
                process.terminate()

        return False

def main():
    """Main launcher function."""
    print_banner()

    # Check if we're in the right directory (should have src/ and config/ folders)
    if not Path("src").exists() or not Path("config").exists():
        print("❌ src/ or config/ directory not found!")
        print("💡 Please run this script from the Harmoniq root directory")
        print("   (The directory that contains src/ and config/ folders)")
        sys.exit(1)

    # Check for config file
    if not Path("config/config.yaml").exists() and not Path("config/config.yaml.example").exists():
        print("❌ No config file found in config/ directory!")
        print("💡 Please ensure you have config/config.yaml or config/config.yaml.example")
        sys.exit(1)

    # Check requirements
    if not check_requirements():
        sys.exit(1)

    print("✅ All requirements satisfied!")
    print("")

    # Start services
    if not start_services():
        sys.exit(1)

if __name__ == "__main__":
    main()
