#!/usr/bin/env python
import os
import sys
import subprocess
import platform
from pathlib import Path
import logging

# Add parent directory to path so we can import logo_bot modules
sys.path.append(str(Path(__file__).parent.parent.parent))

from logo_bot.config import CACHE_DIR

# Configure logging
log_dir = os.path.join(CACHE_DIR, "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "cron_setup.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('cron_setup')

def is_cron_installed():
    """Check if cron is installed on the system"""
    try:
        subprocess.run(["which", "cron"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError:
        return False

def is_launchd_available():
    """Check if launchd is available (macOS)"""
    return platform.system() == "Darwin"

def setup_cron_job():
    """Set up a cron job to run the monitoring scripts daily"""
    if not is_cron_installed():
        logger.error("Cron is not installed on this system")
        return False
    
    # Get the absolute path to the monitoring scripts
    check_script = str(Path(__file__).parent / "check_extractors.py")
    update_script = str(Path(__file__).parent / "update_selectors.py")
    
    # Get Python executable path
    python_path = sys.executable
    
    # Create cron job entry (runs at 3 AM daily)
    cron_entry = f"0 3 * * * {python_path} {check_script} >> {log_dir}/cron_check.log 2>&1\n"
    cron_entry += f"30 3 * * * {python_path} {update_script} >> {log_dir}/cron_update.log 2>&1\n"
    
    # Add to crontab
    try:
        # Get existing crontab
        proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        current_crontab = proc.stdout
        
        # Check if our jobs are already in the crontab
        if check_script in current_crontab:
            logger.info("Cron job already exists")
            return True
        
        # Add our entries
        new_crontab = current_crontab + cron_entry
        
        # Write to a temporary file
        temp_file = "/tmp/logo_bot_crontab"
        with open(temp_file, "w") as f:
            f.write(new_crontab)
        
        # Install the new crontab
        subprocess.run(["crontab", temp_file], check=True)
        
        logger.info("Cron job set up successfully")
        return True
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Error setting up cron job: {str(e)}")
        return False

def setup_launchd_job():
    """Set up a launchd job to run the monitoring scripts daily (macOS)"""
    if not is_launchd_available():
        logger.error("Launchd is not available on this system")
        return False
    
    # Get the absolute paths
    check_script = str(Path(__file__).parent / "check_extractors.py")
    update_script = str(Path(__file__).parent / "update_selectors.py")
    python_path = sys.executable
    
    # Create plist directory if it doesn't exist
    plist_dir = os.path.expanduser("~/Library/LaunchAgents")
    os.makedirs(plist_dir, exist_ok=True)
    
    # Create plist files
    check_plist_path = os.path.join(plist_dir, "com.logo-bot.check-extractors.plist")
    update_plist_path = os.path.join(plist_dir, "com.logo-bot.update-selectors.plist")
    
    # Create check extractors plist
    check_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.logo-bot.check-extractors</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{check_script}</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{log_dir}/launchd_check.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/launchd_check_error.log</string>
</dict>
</plist>
"""
    
    # Create update selectors plist
    update_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.logo-bot.update-selectors</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{update_script}</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{log_dir}/launchd_update.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/launchd_update_error.log</string>
</dict>
</plist>
"""
    
    try:
        # Write plist files
        with open(check_plist_path, "w") as f:
            f.write(check_plist)
        with open(update_plist_path, "w") as f:
            f.write(update_plist)
        
        # Load the launchd jobs
        subprocess.run(["launchctl", "load", check_plist_path], check=True)
        subprocess.run(["launchctl", "load", update_plist_path], check=True)
        
        logger.info("LaunchAgent jobs set up successfully")
        return True
    
    except Exception as e:
        logger.error(f"Error setting up LaunchAgent jobs: {str(e)}")
        return False

def main():
    """Main function to set up scheduled monitoring"""
    logger.info("Setting up scheduled monitoring for logo extractors")
    
    system = platform.system()
    
    if system == "Darwin":  # macOS
        logger.info("Detected macOS, using launchd")
        success = setup_launchd_job()
    elif system == "Linux" or system == "FreeBSD":
        logger.info(f"Detected {system}, using cron")
        success = setup_cron_job()
    else:
        logger.error(f"Unsupported system: {system}")
        logger.info("Please set up scheduled tasks manually for Windows or other systems")
        sys.exit(1)
    
    if success:
        logger.info("Monitoring scheduled successfully")
    else:
        logger.error("Failed to schedule monitoring")
        sys.exit(1)

if __name__ == "__main__":
    main() 