#!/usr/bin/env python3

import os
import subprocess
import sys
import platform
import json
import socket
from pathlib import Path
import getpass
import tempfile
import stat
import re

# --- Helper Functions ---

def get_yes_no_input(prompt, default=None):
    """Get validated yes/no input from user with better UX"""
    while True:
        if default is not None:
            default_text = "Y/n" if default else "y/N"
            response = input(f"{prompt} ({default_text}): ").strip().lower()
            if not response:
                return default
        else:
            response = input(f"{prompt} (y/n): ").strip().lower()
        
        if response in ['y', 'yes', 'true', '1']:
            return True
        elif response in ['n', 'no', 'false', '0']:
            return False
        else:
            print("❌ Please enter 'y' for yes or 'n' for no.")

def get_validated_input(prompt, validator=None, error_msg="Invalid input. Please try again.", required=True):
    """Get validated input with custom validation function"""
    while True:
        try:
            response = input(f"{prompt}: ").strip()
            if not required and not response:
                return response
            if required and not response:
                print("❌ This field is required.")
                continue
            if validator and not validator(response):
                print(f"❌ {error_msg}")
                continue
            return response
        except KeyboardInterrupt:
            print("\n\n❌ Operation cancelled by user.")
            sys.exit(1)

def run(cmd, check=True, capture=False):
    """Enhanced run function with better progress feedback"""
    print(f"🔄 [RUNNING] {cmd}")
    res = subprocess.run(cmd, shell=True, text=True,
                         stdout=subprocess.PIPE if capture else None,
                         stderr=subprocess.PIPE if capture else None)
    out = res.stdout.strip() if res.stdout else ''
    err = res.stderr.strip() if res.stderr else ''
    if check and res.returncode != 0:
        print(f"❌ [ERROR] Command failed: {cmd}")
        if err:
            print(f"   Error details: {err}")
        sys.exit(res.returncode)
    elif res.returncode == 0 and not capture:
        print(f"✅ [SUCCESS] Command completed")
    return out if capture else None

def print_step(message, step_num=None, total_steps=None):
    """Print formatted step with progress indicator"""
    if step_num and total_steps:
        progress = f"[{step_num}/{total_steps}]"
        print(f"\n🚀 {progress} {message}")
    else:
        print(f"\n🚀 [STEP] {message}")

def print_info(message):
    """Print info message with consistent formatting"""
    print(f"ℹ️  [INFO] {message}")

def print_warning(message):
    """Print warning message with consistent formatting"""
    print(f"⚠️  [WARN] {message}")

def print_error(message):
    """Print error message with consistent formatting"""
    print(f"❌ [ERROR] {message}")

def print_success(message):
    """Print success message with consistent formatting"""
    print(f"✅ [SUCCESS] {message}")

def safe_mkdir(p: Path):
    if not p.exists():
        try:
            p.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            run(f"sudo mkdir -p {p}")
        except Exception as e:
            print_warning(f"Could not create directory {p}: {e}")

def is_installed(cmd):
    return subprocess.call(f"command -v {cmd}", shell=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()

def is_mount_point(path):
    """Check if a path is a mount point"""
    try:
        return Path(path).is_mount()
    except:
        # Fallback: check if it appears in /proc/mounts
        try:
            mounts = run("cat /proc/mounts", capture=True, check=False)
            return str(path) in mounts
        except:
            return False

# --- PIA VPN Setup ---

def get_platform_tag():
    sysn = platform.system().lower()
    mach = platform.machine().lower()
    if sysn == 'linux':
        if 'arm64' in mach or 'aarch64' in mach:
            return 'linux-arm64'
        if 'arm' in mach:
            return 'linux-armhf'
        return 'linux'
    if sysn == 'darwin':
        return 'macos'
    if sysn == 'windows':
        if 'arm' in mach:
            return 'windows-arm64'
        if '64' in mach:
            return 'windows-x64'
        return 'windows-x86'
    return None

def find_local_installer():
    tag = get_platform_tag()
    ext_map = {
        'linux': 'run',
        'linux-arm64': 'run',
        'linux-armhf': 'run',
        'macos': 'zip',
        'windows-x64': 'exe',
        'windows-arm64': 'exe',
        'windows-x86': 'exe'
    }
    ext = ext_map.get(tag)
    if not ext:
        print_error(f"Unsupported platform: {tag}")
        sys.exit(1)
    installers = list(Path(__file__).parent.glob(f"pia-{tag}-*.{ext}"))
    if not installers:
        print_error(f"No installer for pia-{tag}*.{ext}")
        sys.exit(1)
    return installers[0]

def install_pia():
    if is_installed('piactl'):
        print_info('piactl already installed')
        return
    try:
        inst = find_local_installer()
    except SystemExit:
        print_error("No PIA installer found for your system in this directory.")
        print("Please download the appropriate installer from:")
        print("  https://github.com/Blackkingsman/media_server_setup/releases")
        print("and place it in this directory, then rerun the script.")
        sys.exit(1)
    print_step(f"Installing PIA via {inst.name}")
    if not (inst.stat().st_mode & stat.S_IXUSR):
        inst.chmod(inst.stat().st_mode | stat.S_IXUSR)
    run(str(inst))

def login_pia():
    print_step("Checking PIA connection...")
    proc = subprocess.run('piactl connect', shell=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = (proc.stdout or '') + (proc.stderr or '')
    if proc.returncode == 0:
        print_success(out.strip() or 'PIA connected successfully')
        return
    if 'requires a logged in account' not in out.lower():
        print_error(f"Unexpected error: {out.strip()}")
        sys.exit(proc.returncode)
    print_info('Not logged in; prompting for credentials')
    user = input('PIA Username: ')
    pwd = getpass.getpass('PIA Password: ')
    with tempfile.NamedTemporaryFile('w', delete=False) as tf:
        tf.write(user + '\n' + pwd + '\n')
        tf.flush()
        cred = tf.name
    os.chmod(cred, 0o600)
    run(f"piactl login {cred}")
    os.remove(cred)
    run('piactl connect')
    run('piactl get connectionstate')

# --- Docker & NVIDIA Setup ---

def install_docker():
    if is_installed('docker') and is_installed('docker-compose'):
        print_info('Docker & Docker Compose already installed')
        return
    print_step("Installing Docker and required components...")
    run('sudo apt update')
    run('sudo apt install -y docker.io docker-compose nvidia-container-runtime')
    run('sudo systemctl enable docker --now')
    run(f"sudo usermod -aG docker {os.getlogin()}")
    print_success("Docker installation complete!")

def configure_nvidia_docker():
    if is_installed('nvidia-container-runtime'):
        run('sudo nvidia-ctk runtime configure --runtime=docker')
        run('sudo systemctl daemon-reload && sudo systemctl restart docker')

def check_nvidia_driver():
    if not is_installed('nvidia-smi'):
        return False
    return 'Driver Version' in run('nvidia-smi', capture=True)

def install_nvidia_driver():
    run("sudo apt-get purge -y '^nvidia-.*'")
    run('sudo apt install -y ubuntu-drivers-common')
    recs = [l for l in run('ubuntu-drivers devices', capture=True).splitlines() if 'recommended' in l]
    if not recs:
        print_error('No recommended NVIDIA driver found')
        sys.exit(1)
    drv = recs[0].split()[0]
    run(f"sudo apt install -y {drv}")
    print_info('NVIDIA driver installed. Reboot required!')
    sys.exit(0)

def install_nvidia_container_toolkit():
    if not is_installed('nvidia-container-toolkit'):
        run('sudo apt install -y nvidia-container-toolkit')
        configure_nvidia_docker()

def detect_cuda_version():
    for l in run('nvidia-smi', capture=True).splitlines():
        if 'CUDA Version' in l:
            v = l.split('CUDA Version:')[-1].split()[0]
            return v if v.count('.') == 2 else v + '.0'
    return None

def test_docker_gpu(ver):
    img = f"nvidia/cuda:{ver}-base-ubuntu22.04"
    try:
        run(f"sudo docker run --rm --runtime=nvidia --gpus all {img} nvidia-smi")
    except Exception:
        configure_nvidia_docker()
        run(f"sudo docker run --rm --runtime=nvidia --gpus all {img} nvidia-smi")

def install_nvidia_patch():
    # Get the driver version from nvidia-smi
    nvsmi = run("nvidia-smi", capture=True)
    version = None
    for line in nvsmi.splitlines():
        if "Driver Version" in line:
            version = line.split("Driver Version:")[1].split()[0]
            break
    if not version:
        print_error("Could not determine NVIDIA driver version.")
        return
    print_info(f"Detected NVIDIA driver version: {version}")
    # Format the download URL
    url = f"https://international.download.nvidia.com/XFree86/Linux-x86_64/{version}/NVIDIA-Linux-x86_64-{version}.run"
    print_info(f"Patch download URL: {url}")
    if not get_yes_no_input("🔧 Download and install the NVIDIA transcoding patch?", default=False):
        print_info("Skipping NVIDIA patch installation.")
        return
    run("sudo mkdir -p /opt/nvidia && cd /opt/nvidia", check=True)
    run(f"cd /opt/nvidia && sudo wget {url}", check=True)
    run(f"cd /opt/nvidia && sudo chmod +x ./NVIDIA-Linux-x86_64-{version}.run", check=True)
    print_info("Running the NVIDIA installer. Follow the prompts in the installer window.")
    run(f"cd /opt/nvidia && sudo ./NVIDIA-Linux-x86_64-{version}.run", check=True)

# --- Storage Pool Functions ---

def add_drive_to_pool(media_root):
    """Add new drives to existing storage pool without disrupting current setup"""
    print_step("Adding drives to existing storage pool")
    
    # Get all block devices
    data = json.loads(run('lsblk -J -o NAME,SIZE,MODEL,FSTYPE,MOUNTPOINT,TYPE', capture=True))
    
    def collect_available_drives(nodes):
        """Collect drives that can be added to the pool"""
        available = []
        for node in nodes:
            # Only look at actual disk devices, not partitions
            if node.get('type') == 'disk':
                device_name = node['name']
                device_path = f"/dev/{device_name}"
                
                # Check if this disk has any children (partitions)
                children = node.get('children', [])
                
                if not children:
                    # No partitions - completely blank drive
                    available.append({
                        'name': device_name,
                        'path': device_path,
                        'size': node.get('size', 'Unknown'),
                        'model': node.get('model', 'Unknown'),
                        'fstype': 'Unformatted',
                        'mountpoint': None,
                        'status': 'Blank drive (no partitions)'
                    })
                else:
                    # Has partitions - check if any are unmounted and available
                    for child in children:
                        child_path = f"/dev/{child['name']}"
                        if not child.get('mountpoint'):  # Unmounted partition
                            available.append({
                                'name': child['name'],
                                'path': child_path,
                                'size': child.get('size', node.get('size', 'Unknown')),
                                'model': node.get('model', 'Unknown'),
                                'fstype': child.get('fstype', 'Unformatted'),
                                'mountpoint': None,
                                'status': 'Unmounted partition'
                            })
        return available
    
    available_drives = collect_available_drives(data['blockdevices'])
    
    # Get current pool drives to exclude them
    pool_drives = set()
    try:
        # Check what's currently in the mergerfs pool
        mounts_output = run("cat /proc/mounts", capture=True, check=False)
        for line in mounts_output.splitlines():
            if 'fuse.mergerfs' in line and media_root in line:
                # Extract source paths from mergerfs mount
                sources = line.split()[0].split(':')
                for source in sources:
                    if source.startswith('/mnt/'):
                        # Get the device mounted at this source
                        mount_info = run(f"findmnt -n -o SOURCE {source}", capture=True, check=False)
                        if mount_info:
                            device = mount_info.strip()
                            if device.startswith('/dev/'):
                                # Extract base device name (remove partition numbers)
                                base_device = device.rstrip('0123456789')
                                pool_drives.add(base_device.split('/')[-1])
                                pool_drives.add(device.split('/')[-1])
    except:
        print_warning("Could not determine current pool drives")
    
    # Also check /mnt/ mounts directly
    try:
        existing_mounts = run("mount | grep /mnt/", capture=True, check=False).splitlines()
        for mount_line in existing_mounts:
            if '/dev/' in mount_line:
                device = mount_line.split()[0]
                if device.startswith('/dev/'):
                    device_name = device.split('/')[-1]
                    base_device = device_name.rstrip('0123456789')
                    pool_drives.add(device_name)
                    pool_drives.add(base_device)
    except:
        pass
    
    # Filter out drives already in use
    available_drives = [d for d in available_drives if d['name'] not in pool_drives]
    
    if not available_drives:
        print_warning("No available drives found to add to the pool.")
        print("\n📝 All drives appear to be either:")
        print("  • Already part of the storage pool")
        print("  • Currently mounted elsewhere")
        print("  • System drives in use")
        print("\n💡 If you have new drives, make sure they're:")
        print("  • Properly connected and detected by the system")
        print("  • Not mounted elsewhere")
        print("  • Not containing important data")
        return
    
    print("\n" + "="*80)
    print("💿 AVAILABLE DRIVES TO ADD")
    print("="*80)
    print(f"{'#':<3} {'Device':<15} {'Size':<10} {'Type':<12} {'Model':<20} {'Status'}")
    print("-" * 80)
    
    for i, drive in enumerate(available_drives):
        # Safely handle None values
        size = drive['size'] if drive['size'] else 'Unknown'
        model = (drive['model'] if drive['model'] else 'Unknown')[:19]
        fstype = drive['fstype'] if drive['fstype'] else 'Unknown'
        status = drive['status'][:25]
        
        print(f"{i:<3} {drive['path']:<15} {size:<10} {fstype:<12} {model:<20} {status}")
    
    print("-" * 70)
    print("💡 Select multiple drives by separating numbers with commas (e.g., 0,1,2)")
    print("⚠️  All data on selected drives will be LOST!")
    
    # Get user selection
    while True:
        try:
            selection = input(f"\n🎯 Select drives to add (0-{len(available_drives)-1}) or 'q' to quit: ").strip()
            if selection.lower() == 'q':
                print_info("Drive addition cancelled.")
                return
            
            drive_indices = [int(x.strip()) for x in selection.split(',')]
            
            # Validate indices
            invalid_indices = [idx for idx in drive_indices if idx < 0 or idx >= len(available_drives)]
            if invalid_indices:
                print_error(f"Invalid selections: {invalid_indices}. Please enter numbers 0-{len(available_drives)-1}")
                continue
            
            selected_drives = [available_drives[idx] for idx in drive_indices]
            
            print(f"\n📋 Selected drives:")
            for drive in selected_drives:
                device_path = f"/dev/{drive['name']}"
                print(f"   • {device_path} ({drive['size']}) - {drive.get('model', 'Unknown')}")
            
            # Filesystem selection
            print(f"\n📝 Filesystem options:")
            print(f"  1. ext4 (recommended for media)")
            print(f"  2. xfs (good for large files)")
            print(f"  3. btrfs (advanced features)")
            
            while True:
                fs_choice = input(f"\n🎯 Select filesystem for all drives (1-3): ").strip()
                if fs_choice == '1':
                    filesystem = 'ext4'
                    break
                elif fs_choice == '2':
                    filesystem = 'xfs'
                    break
                elif fs_choice == '3':
                    filesystem = 'btrfs'
                    break
                else:
                    print_error("Please enter 1, 2, or 3")
            
            # Final confirmation
            total_size = sum([float(d['size'].replace('G', '').replace('T', '000').replace('M', '0.001')) for d in selected_drives if d['size']])
            
            print(f"\n⚠️  FINAL CONFIRMATION:")
            print(f"   • Number of drives: {len(selected_drives)}")
            print(f"   • Filesystem: {filesystem}")
            print(f"   • Approximate total size: {total_size:.1f}GB")
            print(f"   • ALL DATA ON THESE DRIVES WILL BE LOST!")
            
            if get_yes_no_input(f"\n❓ Proceed with formatting {len(selected_drives)} drive(s)?", default=False):
                break
            else:
                continue
                
        except ValueError:
            print_error("Please enter valid numbers separated by commas.")
        except KeyboardInterrupt:
            print("\n\n❌ Operation cancelled.")
            return
    
    # Process all drives
    new_mount_points = []
    
    for i, drive in enumerate(selected_drives, 1):
        device_path = f"/dev/{drive['name']}"
        drive_name = drive['name']
        mount_point = Path(f"/mnt/{drive_name}")
        
        try:
            print_step(f"Processing drive {i}/{len(selected_drives)}: {device_path}")
            
            # Unmount if somehow mounted
            run(f"sudo umount {device_path}", check=False)
            
            # Create partition table and partition
            print_info("Creating partition table...")
            run(f"sudo parted {device_path} --script mklabel gpt")
            run(f"sudo parted {device_path} --script mkpart primary 0% 100%")
            
            # Wait a moment for partition to be recognized
            run("sleep 2")
            
            # Format the partition
            partition_path = f"{device_path}1"
            print_info(f"Formatting {partition_path} as {filesystem}...")
            
            if filesystem == 'ext4':
                run(f"sudo mkfs.ext4 -F {partition_path}")
            elif filesystem == 'xfs':
                run(f"sudo mkfs.xfs -f {partition_path}")
            elif filesystem == 'btrfs':
                run(f"sudo mkfs.btrfs -f {partition_path}")
            
            # Create mount point
            safe_mkdir(mount_point)
            
            # Get UUID of new partition
            uuid = run(f"sudo blkid -s UUID -o value {partition_path}", capture=True)
            if not uuid:
                print_error(f"Could not get UUID of formatted partition {partition_path}")
                continue
            
            print_info(f"New partition UUID: {uuid}")
            
            # Add to fstab
            mount_opts = "defaults,nofail"
            fstab_entry = f"UUID={uuid} {mount_point} {filesystem} {mount_opts} 0 0"
            
            print_info("Adding to /etc/fstab...")
            run(f"echo '{fstab_entry}' | sudo tee -a /etc/fstab")
            
            # Mount the new drive
            print_info("Mounting new drive...")
            run(f"sudo mount {mount_point}")
            
            # Set ownership
            run(f"sudo chown 1000:1000 '{mount_point}'")
            
            new_mount_points.append(str(mount_point))
            print_success(f"Successfully processed {device_path}")
            
        except Exception as e:
            print_error(f"Failed to process drive {device_path}: {e}")
            continue
    
    if not new_mount_points:
        print_error("No drives were successfully added.")
        return
    
    # Update mergerfs pool with all new drives
    print_step("Updating storage pool configuration")
    
    try:
        # Get CURRENT mergerfs mount from /proc/mounts (this is the REAL current state)
        mounts_output = run("cat /proc/mounts", capture=True)
        current_mergerfs_sources = None
        
        for line in mounts_output.splitlines():
            if 'fuse.mergerfs' in line and media_root in line:
                current_mergerfs_sources = line.split()[0]  # Get the actual current sources
                print_info(f"Current pool sources: {current_mergerfs_sources}")
                break
        
        if not current_mergerfs_sources:
            print_error("Could not find existing mergerfs mount. Manual configuration needed.")
            print(f"New drives mounted at: {', '.join(new_mount_points)}")
            return
        
        # Build new sources by appending to current ones
        new_sources = f"{current_mergerfs_sources}:{':'.join(new_mount_points)}"
        print_info(f"New pool sources: {new_sources}")
        
        # Update fstab with new mergerfs configuration
        print_info("Updating mergerfs configuration in /etc/fstab...")
        
        # Read current fstab
        fstab_content = run("cat /etc/fstab", capture=True)
        updated_fstab = []
        
        for line in fstab_content.splitlines():
            if 'fuse.mergerfs' in line and media_root in line:
                # Replace the old mergerfs line with updated sources
                parts = line.split()
                if len(parts) >= 6:
                    parts[0] = new_sources  # Update the sources part
                    updated_line = ' '.join(parts)
                    updated_fstab.append(updated_line)
                    print_info(f"Updated mergerfs line: {updated_line}")
                else:
                    updated_fstab.append(line)
            else:
                updated_fstab.append(line)
        
        # Write updated fstab
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_fstab:
            tmp_fstab.write('\n'.join(updated_fstab) + '\n')
            tmp_fstab_path = tmp_fstab.name
        
        run(f"sudo cp {tmp_fstab_path} /etc/fstab")
        os.unlink(tmp_fstab_path)
        
        # Remount mergerfs pool with new configuration
        print_info("Remounting storage pool with new drives...")
        run(f"sudo umount {media_root}")
        run(f"sudo mount {media_root}")
        
        print_success(f"🎉 Successfully added {len(new_mount_points)} drive(s) to storage pool!")
        print(f"   • New drives: {', '.join(new_mount_points)}")
        print(f"   • Storage pool updated: {media_root}")
        
        # Automatically run pool recovery to ensure proper configuration
        print_step("Running automatic pool recovery to ensure proper configuration...")
        try:
            # Automatically run the repair that worked for the user (Option 21)
            print_info("🔄 Automatically rebuilding pool with new drives...")
            repair_storage_pool()
            print_success("✅ Pool recovery completed successfully!")
        except Exception as recovery_error:
            print_warning(f"Pool recovery encountered an issue: {recovery_error}")
            print_info("Pool may still function, but consider running manual recovery (option 21) if issues persist.")
        
        # Show final pool status
        pool_usage = run(f"df -h {media_root}", capture=True, check=False)
        print(f"\n📊 Final pool status:")
        for line in pool_usage.splitlines():
            if media_root in line:
                print(f"   {line}")
        
    except Exception as e:
        print_error(f"Failed to update pool configuration: {e}")
        print("New drives were mounted individually. You may need to manually update mergerfs.")

def remove_drives_from_pool(media_root):
    """Remove drives from existing storage pool"""
    print_step("Removing drives from storage pool")
    
    # Get current pool drives
    mounts_output = run("cat /proc/mounts", capture=True)
    pool_drives = []
    
    # Find drives that are part of the pool
    for line in mounts_output.splitlines():
        if '/mnt/' in line and line.startswith('/dev/'):
            parts = line.split()
            device = parts[0]
            mount_point = parts[1]
            if mount_point.startswith('/mnt/') and mount_point != media_root:
                # Get drive info
                device_name = device.split('/')[-1].rstrip('1234567890')  # Remove partition numbers
                size_output = run(f"lsblk -n -o SIZE {device}", capture=True, check=False)
                size = size_output.strip() if size_output else "Unknown"
                pool_drives.append({
                    'device': device,
                    'mount_point': mount_point,
                    'device_name': device_name,
                    'size': size
                })
    
    if not pool_drives:
        print_warning("No drives found in the current storage pool.")
        return
    
    print("\n" + "="*70)
    print("📤 DRIVES IN CURRENT POOL")
    print("="*70)
    print(f"{'#':<3} {'Device':<15} {'Mount Point':<15} {'Size':<10}")
    print("-" * 70)
    
    for i, drive in enumerate(pool_drives):
        print(f"{i:<3} {drive['device']:<15} {drive['mount_point']:<15} {drive['size']:<10}")
    
    print("-" * 70)
    print("💡 Select multiple drives by separating numbers with commas (e.g., 0,1,2)")
    print("⚠️  Data will be preserved but drives will be removed from the pool!")
    
    # Get user selection
    while True:
        try:
            selection = input(f"\n🎯 Select drives to remove (0-{len(pool_drives)-1}) or 'q' to quit: ").strip()
            if selection.lower() == 'q':
                print_info("Drive removal cancelled.")
                return
            
            drive_indices = [int(x.strip()) for x in selection.split(',')]
            
            # Validate indices
            invalid_indices = [idx for idx in drive_indices if idx < 0 or idx >= len(pool_drives)]
            if invalid_indices:
                print_error(f"Invalid selections: {invalid_indices}. Please enter numbers 0-{len(pool_drives)-1}")
                continue
            
            if len(drive_indices) >= len(pool_drives):
                print_error("Cannot remove all drives from the pool. At least one drive must remain.")
                continue
            
            selected_drives = [pool_drives[idx] for idx in drive_indices]
            
            print(f"\n📋 Drives to remove:")
            for drive in selected_drives:
                print(f"   • {drive['device']} mounted at {drive['mount_point']} ({drive['size']})")
            
            # Check for data
            data_warning = False
            for drive in selected_drives:
                try:
                    contents = run(f"ls -la '{drive['mount_point']}'", capture=True, check=False)
                    if contents and len(contents.splitlines()) > 3:  # More than just . and ..
                        data_warning = True
                        break
                except:
                    pass
            
            if data_warning:
                print("⚠️  Some drives contain data. Make sure to back up or move important files!")
            
            # Final confirmation
            print(f"\n❓ This will:")
            print(f"   • Remove {len(selected_drives)} drive(s) from the pool")
            print(f"   • Unmount the drives")
            print(f"   • Remove entries from /etc/fstab")
            print(f"   • Update mergerfs configuration")
            print(f"   • Data on drives will be preserved but inaccessible through the pool")
            
            if get_yes_no_input(f"\n❓ Proceed with removing {len(selected_drives)} drive(s)?", default=False):
                break
            else:
                continue
                
        except ValueError:
            print_error("Please enter valid numbers separated by commas.")
        except KeyboardInterrupt:
            print("\n\n❌ Operation cancelled.")
            return
    
    # Remove drives
    removed_mount_points = []
    
    for i, drive in enumerate(selected_drives, 1):
        try:
            print_step(f"Removing drive {i}/{len(selected_drives)}: {drive['device']}")
            
            # Unmount the drive
            print_info(f"Unmounting {drive['mount_point']}...")
            run(f"sudo umount '{drive['mount_point']}'")
            
            # Remove mount point directory
            try:
                Path(drive['mount_point']).rmdir()
                print_info(f"Removed directory {drive['mount_point']}")
            except:
                print_warning(f"Could not remove directory {drive['mount_point']} (may contain files)")
            
            removed_mount_points.append(drive['mount_point'])
            print_success(f"Successfully unmounted {drive['device']}")
            
        except Exception as e:
            print_error(f"Failed to unmount drive {drive['device']}: {e}")
            continue
    
    if not removed_mount_points:
        print_error("No drives were successfully removed.")
        return
    
    # Update fstab and mergerfs configuration
    print_step("Updating system configuration")
    
    try:
        # Read current fstab
        fstab_content = run("cat /etc/fstab", capture=True)
        updated_fstab = []
        
        # Get devices to remove from fstab
        devices_to_remove = [drive['device'] for drive in selected_drives]
        mount_points_to_remove = set(removed_mount_points)
        
        for line in fstab_content.splitlines():
            should_remove = False
            
            # Check if this line is for a removed drive
            for device in devices_to_remove:
                if device in line:
                    should_remove = True
                    break
            
            # Check if this line is for a removed mount point
            for mount_point in mount_points_to_remove:
                if mount_point in line and not 'fuse.mergerfs' in line:
                    should_remove = True
                    break
            
            # Handle mergerfs line
            if 'fuse.mergerfs' in line and media_root in line:
                parts = line.split()
                if len(parts) >= 6:
                    current_sources = parts[0].split(':')
                    # Remove the mount points that were removed
                    new_sources = [src for src in current_sources if src not in mount_points_to_remove]
                    if new_sources:
                        parts[0] = ':'.join(new_sources)
                        updated_line = ' '.join(parts)
                        updated_fstab.append(updated_line)
                        print_info(f"Updated mergerfs configuration")
                    else:
                        print_error("All sources removed from mergerfs - this should not happen!")
                        updated_fstab.append(line)
                else:
                    updated_fstab.append(line)
            elif not should_remove:
                updated_fstab.append(line)
            else:
                print_info(f"Removed fstab entry: {line[:50]}...")
        
        # Write updated fstab
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_fstab:
            tmp_fstab.write('\n'.join(updated_fstab) + '\n')
            tmp_fstab_path = tmp_fstab.name
        
        run(f"sudo cp {tmp_fstab_path} /etc/fstab")
        os.unlink(tmp_fstab_path)
        
        # Remount mergerfs pool
        print_info("Remounting storage pool...")
        run(f"sudo umount {media_root}")
        run(f"sudo mount {media_root}")
        
        print_success(f"🎉 Successfully removed {len(removed_mount_points)} drive(s) from storage pool!")
        print(f"   • Removed drives: {', '.join(removed_mount_points)}")
        print(f"   • Storage pool updated: {media_root}")
        
        # Show updated pool status
        pool_usage = run(f"df -h {media_root}", capture=True)
        print(f"\n📊 Updated pool status:")
        for line in pool_usage.splitlines():
            if media_root in line:
                print(f"   {line}")
        
        print(f"\n💡 Removed drives are still available as individual devices if needed.")
        
    except Exception as e:
        print_error(f"Failed to update configuration: {e}")
        print("Drives were unmounted but configuration may need manual cleanup.")

def ensure_config_directories():
    home = Path.home()
    config_root = home / "configfiles"
    config_subs = [
        'jellyfinconfig',
        'jellyfinconfig/cache',
        'radarrconfig',
        'sonarrconfig',
        'jellyseerrconfig',
        'sabnzbdconfig'
    ]
    for s in config_subs:
        p = config_root / s
        safe_mkdir(p)
        if not p.exists():
            print_error(f"Directory {p} could not be created. Check your mount and permissions.")
            sys.exit(1)
        run(f"sudo chown 1000:1000 '{p}'")
    for d in ['/docker/tdarr/server', '/docker/tdarr/configs', '/docker/tdarr/logs']:
        p = Path(d)
        safe_mkdir(p)
        if not p.exists():
            print_error(f"Directory {p} could not be created. Check your mount and permissions.")
            sys.exit(1)
        run(f"sudo chown 1000:1000 '{p}'")

def setup_storage_pool(media_root):
    print_step('Configuring media storage pool...')
    
    # Check if pool already exists
    existing_pool = Path(media_root)
    has_existing_pool = existing_pool.exists() and any(existing_pool.iterdir())
    
    if has_existing_pool:
        print_info(f"Existing media pool detected at {media_root}")
        print("📝 Pool Management Options:")
        print("  1. Add drives to existing pool")
        print("  2. Remove drives from existing pool")
        print("  3. Reconfigure entire pool (destructive)")
        print("  4. Skip pool configuration")
        
        while True:
            choice = input("\n🎯 Select option (1-4): ").strip()
            if choice == '1':
                add_drive_to_pool(media_root)
                return
            elif choice == '2':
                remove_drives_from_pool(media_root)
                return
            elif choice == '3':
                if get_yes_no_input("⚠️  This will unmount and reconfigure the entire pool. Continue?", default=False):
                    break
                else:
                    continue
            elif choice == '4':
                print_info("Skipping pool configuration")
                return
            else:
                print_error("Please enter 1, 2, 3, or 4")
    
    # Original full pool setup code
    BASE_FSTAB = "/etc/fstab.original"
    # Unmount and clear out all current mounts in /mnt
    for m in Path('/mnt').iterdir():
        if m.is_mount():
            run(f'sudo umount {m}', check=False)
        if m.exists() and m.is_dir():
            try:
                m.rmdir()
            except OSError:
                pass
    if not get_yes_no_input('Reconfigure storage pool?', default=True):
        print_info('Skipping pool configuration')
        return
    if not Path(BASE_FSTAB).exists():
        run(f'sudo cp /etc/fstab {BASE_FSTAB}')
    run(f"sudo cp {BASE_FSTAB} /etc/fstab")
    data = json.loads(run('lsblk -J -o NAME,SIZE,MODEL,FSTYPE,MOUNTPOINT', capture=True))
    def collect(nodes):
        out = []
        for n in nodes:
            if n.get('fstype'):
                out.append(n)
            if n.get('children'):
                out.extend(collect(n['children']))
        return out
    devs = collect(data['blockdevices'])
    
    print("\n" + "="*80)
    print("📂 AVAILABLE STORAGE DEVICES")
    print("="*80)
    
    # Display devices in a nice table format
    if not devs:
        print_error("No block devices found!")
        return
    
    print(f"{'#':<3} {'Device':<12} {'Size':<10} {'Type':<8} {'Model':<20} {'UUID'}")
    print("-" * 80)
    
    for i, d in enumerate(devs):
        path = f"/dev/{d['name']}"
        uuid = run(f"blkid -s UUID -o value {path}", capture=True) or "N/A"
        model = d.get('model', 'Unknown')[:19]
        print(f"{i:<3} {path:<12} {d['size']:<10} {d['fstype']:<8} {model:<20} {uuid[:8]}...")
    
    print("-" * 80)
    print("💡 Tip: You can select multiple devices by separating numbers with commas (e.g., 0,1,2)")
    print("⚠️  Warning: Only select devices you want to include in the media pool!")
    
    while True:
        try:
            selection = input("\n🎯 Enter device numbers to include in pool: ").strip()
            if not selection:
                print_error("Please select at least one device.")
                continue
            
            idxs = [int(x.strip()) for x in selection.split(',')]
            
            # Validate all indices
            invalid_indices = [idx for idx in idxs if idx < 0 or idx >= len(devs)]
            if invalid_indices:
                print_error(f"Invalid device numbers: {invalid_indices}")
                continue
                
            # Show confirmation of selected devices
            print(f"\n📋 Selected devices:")
            for idx in idxs:
                d = devs[idx]
                path = f"/dev/{d['name']}"
                print(f"   • {path} ({d['size']}, {d['fstype']}) - {d.get('model', 'Unknown')}")
            
            if get_yes_no_input("\n❓ Proceed with these devices?", default=True):
                break
            else:
                continue
                
        except ValueError:
            print_error("Please enter valid numbers separated by commas.")
        except KeyboardInterrupt:
            print("\n\n❌ Operation cancelled.")
            return
    
    mnt_paths = []
    for i in idxs:
        d = devs[i]
        path = f"/dev/{d['name']}"
        m = Path(f"/mnt/{d['name']}")
        safe_mkdir(m)

        # Use sudo with blkid and regex to extract the UUID reliably
        blkid_output = run(f"sudo blkid {path}", capture=True).strip()
        uuid_match = re.search(r'UUID="([^"]+)"', blkid_output)
        uuid = uuid_match.group(1) if uuid_match else ''

        if not uuid:
            print_warning(f"Could not extract UUID from {path}. Skipping.")
            continue

        # Set mount options; ext4, xfs, and other Linux filesystems don't accept uid/gid options
        fs_type = d['fstype'].lower()
        if fs_type in ["ext4", "ext3", "ext2", "xfs", "btrfs"]:
            mount_opts = "defaults,nofail"
        else:
            # Only use uid/gid for filesystems that support it (FAT32, NTFS, etc.)
            mount_opts = "defaults,nofail,uid=1000,gid=1000"

        entry = f"UUID={uuid} {m} {d['fstype']} {mount_opts} 0 0"
        run(f"echo '{entry}' | sudo tee -a /etc/fstab")

        mounts = run("mount", capture=True)
        if str(m) in mounts or path in mounts:
            resp = input(f"{m} is already mounted. Unmount and remount? (y/n): ").strip().lower()
            if resp == 'y':
                run(f"sudo umount {m}", check=False)
                run(f"sudo mount {m}")
            else:
                print_info(f"Skipping mount for {m}.")
        else:
            run(f"sudo mount {m}")

        mnt_paths.append(str(m))
    pool = media_root
    safe_mkdir(Path(pool))
    src = ':'.join(mnt_paths)
    run(f"printf '\n# MergerFS pool config\n{src} {pool} fuse.mergerfs defaults,allow_other,use_ino,category.create=mfs,nonempty 0 0\n' | sudo tee -a /etc/fstab")
    run('sudo systemctl daemon-reload')
    run('sudo mount -a')
    print_success(f'Storage pool configured at {pool}')

# --- Service Installer Templates & Logic ---

def get_paths(media_root):
    movies_path = Path(media_root) / "Media/Movies"
    tv_path = Path(media_root) / "Media/TV Shows"
    downloads_path = Path(media_root) / "Media/Downloads"
    return {
        "movies_path": str(movies_path),
        "tv_path": str(tv_path),
        "downloads_path": str(downloads_path),
        "media_root": str(media_root)
    }

def get_templates(paths, gpu_enabled):
    node_name = "TdarrNode"
    server_name = "TdarrServer"
    gpu_flags = "--gpus all --runtime=nvidia --device=/dev/dri:/dev/dri" if gpu_enabled else ""
    home = str(Path.home())
    config_root = f"{home}/configfiles"
    return {
        'radarr': lambda: (
            f"sudo docker run -d --name=radarr "
            f"-e PUID=1000 -e PGID=1000 -e TZ=Etc/UTC "
            f"-p 7878:7878 "
            f"-v \"{config_root}/radarrconfig\":/config "
            f"-v \"{paths['movies_path']}\":/movies "
            f"-v \"{paths['media_root']}\":/media "
            f"-v \"{paths['downloads_path']}\":/downloads "
            f"--restart unless-stopped lscr.io/linuxserver/radarr:latest"
        ),
        'sonarr': lambda: (
            f"sudo docker run -d --name=sonarr "
            f"-e PUID=1000 -e PGID=1000 -e TZ=Etc/UTC "
            f"-p 8989:8989 "
            f"-v \"{paths['media_root']}\":/media "
            f"-v \"{paths['tv_path']}\":/tv "
            f"-v \"{paths['downloads_path']}\":/downloads "
            f"-v \"{config_root}/sonarrconfig\":/config "
            f"--restart unless-stopped lscr.io/linuxserver/sonarr:latest"
        ),
        'tdarr_node': lambda ip, port: (
            f"sudo docker run -d --name=tdarr_node "
            f"-v /docker/tdarr/configs:/app/configs "
            f"-v /docker/tdarr/logs:/app/logs "
            f"-v \"{paths['media_root']}/Media\":/media "
            f"-v \"{paths['media_root']}/Media/transcode_cache\":/temp "
            f"-e 'nodeName={node_name}' -e 'serverIP={ip}' -e 'serverPort={port}' -e inContainer=true "
            f"--network bridge -p 8268:8268 -e TZ=Etc/UTC -e PUID=1000 -e PGID=1000 {gpu_flags} "
            f"--log-opt max-size=10m --log-opt max-file=5 "
            f"--restart unless-stopped ghcr.io/haveagitgat/tdarr_node:latest"
        ),
        'tdarr_server': lambda ip, port: (
            f"sudo docker run -d --name=tdarr_server "
            f"-v /docker/tdarr/server:/app/server "
            f"-v /docker/tdarr/configs:/app/configs "
            f"-v /docker/tdarr/logs:/app/logs "
            f"-v \"{paths['media_root']}/Media\":/media "
            f"-v \"{paths['media_root']}/Media/transcode_cache\":/temp "
            f"-e 'webUIPort={port}' -e 'internalNode=false' -e 'inContainer=true' -e 'nodeName={server_name}' "
            f"--network bridge -p 8265:8265 -p 8266:{port} -e TZ=Etc/UTC -e PUID=1000 -e PGID=1000 {gpu_flags} "
            f"--log-opt max-size=10m --log-opt max-file=5 "
            f"--restart unless-stopped ghcr.io/haveagitgat/tdarr:latest"
        ),
        'watchtower': lambda frm, to, srv, prt, usr, pwd: (
            f"sudo docker run -d --name=watchtower --restart unless-stopped "
            f"-v /var/run/docker.sock:/var/run/docker.sock "
            f"-e WATCHTOWER_NOTIFICATIONS=email "
            f"-e WATCHTOWER_NOTIFICATION_EMAIL_FROM={frm} "
            f"-e WATCHTOWER_NOTIFICATION_EMAIL_TO={to} "
            f"-e WATCHTOWER_NOTIFICATION_EMAIL_SERVER={srv} "
            f"-e WATCHTOWER_NOTIFICATION_EMAIL_SERVER_PORT={prt} "
            f"-e WATCHTOWER_NOTIFICATION_EMAIL_SERVER_USER={usr} "
            f"-e WATCHTOWER_NOTIFICATION_EMAIL_SERVER_PASSWORD={pwd} "
            f"containrrr/watchtower"
        ),
        'jellyseerr': lambda: (
            f"sudo docker run -d --name=jellyseerr "
            f"-e LOG_LEVEL=debug -e TZ=Etc/UTC -p 5055:5055 "
            f"-v \"{config_root}/jellyseerrconfig\":/app/config "
            f"--restart unless-stopped fallenbagel/jellyseerr:latest"
        ),
        'jellyfin': lambda: (
            f"sudo docker run -d --name=jellyfin {gpu_flags} -p 8096:8096 "
            f"-v \"{config_root}/jellyfinconfig\":/config "
            f"-v \"{config_root}/jellyfinconfig/cache\":/cache "
            f"--mount type=bind,source=\"{paths['media_root']}/Media\",target=/media "
            f"--restart unless-stopped lscr.io/linuxserver/jellyfin:latest"
        ),
        'sabnzbd': lambda: (
            f"sudo docker run -d --name=sabnzbd "
            f"-e PUID=1000 -e PGID=1000 -e TZ=Etc/UTC -p 8080:8080 "
            f"-v \"{paths['downloads_path']}\":/downloads "
            f"-v \"{paths['tv_path']}\":/tv "
            f"-v \"{paths['movies_path']}\":/movies "
            f"-v \"{config_root}/sabnzbdconfig\":/config "
            f"--restart unless-stopped lscr.io/linuxserver/sabnzbd:latest"
        ),
        'portainer': lambda: (
            "sudo docker volume create portainer_data && "
            "sudo docker run -d --name=portainer --restart unless-stopped "
            "-p 8000:8000 -p 9443:9443 "
            "-v /var/run/docker.sock:/var/run/docker.sock "
            "-v portainer_data:/data portainer/portainer-ce:latest"
        )
    }

def list_local_ips_shell():
    print("Available network interfaces and IPs:")
    result = run("ip -o -4 addr show | awk '{print $2, $4}'", capture=True)
    iface_map = {}
    idx = 1
    for line in result.splitlines():
        iface, ip_cidr = line.split()
        ip = ip_cidr.split('/')[0]
        if ip.startswith('127.'):
            continue
        print(f"  {idx}. {iface}: {ip}")
        iface_map[str(idx)] = ip
        idx += 1
    return iface_map

def install_services(media_root, gpu_enabled):
    paths = get_paths(media_root)
    templates = get_templates(paths, gpu_enabled)
    existing = run("sudo docker ps -a --format '{{.Names}}'", capture=True).splitlines()
    
    print("\n" + "="*60)
    print("🐳 DOCKER SERVICES INSTALLER")
    print("="*60)
    
    service_descriptions = {
        'jellyfin': 'Media server (like Plex) for streaming movies/TV',
        'radarr': 'Movie collection manager and downloader',
        'sonarr': 'TV show collection manager and downloader', 
        'jellyseerr': 'Request management for Jellyfin',
        'sabnzbd': 'Usenet downloader',
        'tdarr_server': 'Video transcoding server',
        'tdarr_node': 'Video transcoding worker node',
        'watchtower': 'Automatic container updates',
        'portainer': 'Docker management web interface'
    }
    
    for i, name in enumerate(templates.keys(), 1):
        status = '✅ Installed' if name in existing else '⬜ Not installed'
        desc = service_descriptions.get(name, 'Docker service')
        print(f" {i:2}. {status:<15} {name:<15} - {desc}")
    
    print(f"\n📝 Options:")
    print(f"   • Enter numbers (e.g., 1,2,5) to install specific services")
    print(f"   • Enter 'a' to install ALL services")
    print(f"   • Enter 'q' to quit")
    
    while True:
        choice = input('\n🎯 Select services to install: ').strip().lower()
        
        if choice == 'q':
            print_info("Installation cancelled.")
            return
        elif choice == 'a':
            if get_yes_no_input("❓ Install all services?", default=False):
                to_run = list(templates.keys())
                break
            else:
                continue
        else:
            try:
                service_nums = [int(x.strip()) for x in choice.split(',')]
                invalid_nums = [n for n in service_nums if n < 1 or n > len(templates)]
                if invalid_nums:
                    print_error(f"Invalid service numbers: {invalid_nums}")
                    continue
                
                to_run = [list(templates.keys())[n-1] for n in service_nums]
                
                print(f"\n📋 Services to install:")
                for service in to_run:
                    print(f"   • {service}")
                
                if get_yes_no_input("❓ Proceed with installation?", default=True):
                    break
                    
            except ValueError:
                print_error("Please enter valid numbers separated by commas.")
                continue

    # Gather shared prompts if needed
    tdarr_ip, tdarr_port = None, None
    tdarr_node_ip, tdarr_node_port = None, None
    watchtower_args = None
    if any(s in to_run for s in ('tdarr_node', 'tdarr_server')):
        print("Select the IP for Tdarr Server to bind to:")
        iface_map = list_local_ips_shell()
        ip_choice = input(f"Enter number or custom IP [{get_local_ip()}]: ").strip()
        if ip_choice in iface_map:
            tdarr_ip = iface_map[ip_choice]
        elif ip_choice:
            tdarr_ip = ip_choice
        else:
            tdarr_ip = get_local_ip()
        tdarr_port = input("Enter Tdarr server port [8266]: ").strip() or "8266"
        tdarr_node_ip = tdarr_ip
        tdarr_node_port = tdarr_port
        if 'tdarr_node' in to_run:
            use_external = input("Is the Tdarr server external? (y/n): ").strip().lower() == 'y'
            if use_external:
                tdarr_node_ip = input("Enter external Tdarr server IP: ").strip()
                tdarr_node_port = input("Enter external Tdarr server port [8266]: ").strip() or "8266"
    if 'watchtower' in to_run:
        frm = input("Watchtower email FROM: ")
        to = input("Watchtower email TO: ")
        srv = input("Watchtower SMTP server: ")
        prt = input("Watchtower SMTP port [587]: ").strip() or "587"
        usr = frm
        pwd = getpass.getpass("Watchtower SMTP password: ")
        watchtower_args = (frm, to, srv, prt, usr, pwd)

    for svc in to_run:
        if svc in existing:
            print_info(f"Reinstalling {svc}...")
            run(f"sudo docker stop {svc}")
            run(f"sudo docker rm {svc}")
        if svc == 'tdarr_server':
            cmd = templates[svc](tdarr_ip, tdarr_port)
        elif svc == 'tdarr_node':
            cmd = templates[svc](tdarr_node_ip, tdarr_node_port)
        elif svc == 'watchtower':
            cmd = templates[svc](*watchtower_args)
        else:
            cmd = templates[svc]()
        print_step(f"Installing {svc}...")
        run(cmd)
    print_success('Service installation complete!')

# --- Main Flow ---

def show_main_menu():
    """Display the main menu with all available options"""
    print("\n" + "="*80)
    print("🎬 MEDIA SERVER MANAGEMENT")
    print("="*80)
    print("Choose what you want to do:")
    print()
    print("📦 SETUP & INSTALLATION")
    print("  1. Complete initial setup (full wizard)")
    print("  2. Complete setup with custom service selection")
    print("  3. Install Docker & dependencies only")
    print("  4. Configure NVIDIA GPU support")
    print("  5. Install & configure PIA VPN")
    print()
    print("💾 STORAGE MANAGEMENT")
    print("  6. Set up new storage pool")
    print("  7. Add drives to existing pool")
    print("  8. Remove drives from existing pool")
    print("  9. View storage pool status")
    print()
    print("🐳 SERVICE MANAGEMENT")
    print(" 10. Install services (with selection)")
    print(" 11. Start all services")
    print(" 12. Stop all services")
    print(" 13. Restart all services")
    print(" 14. View service status")
    print(" 15. Remove services")
    print()
    print("🔧 MAINTENANCE")
    print(" 16. Update all containers")
    print(" 17. Clean up unused Docker resources")
    print(" 18. View system information")
    print(" 19. Create directories")
    print(" 20. Debug storage information")
    print(" 21. Repair storage pool")
    print(" 22. Recover corrupted pool (non-destructive)")
    print(" 23. Manual drive recovery (step-by-step)")
    print()
    print(" 0. Exit")
    print("="*80)

def get_media_root():
    """Get the media root path, with smart detection"""
    # Try to detect existing pool
    common_paths = ["/mnt/pool", "/mnt/media", "/media", "/srv/media"]
    for path in common_paths:
        if Path(path).exists() and is_mount_point(path):
            print_info(f"Detected existing media pool at: {path}")
            if get_yes_no_input(f"Use {path} as media root?", default=True):
                return path
    
    # Ask user to specify
    return get_validated_input(
        "📁 Enter media root path",
        validator=lambda x: Path(x).exists() or get_yes_no_input(f"Path {x} doesn't exist. Create it?", default=True),
        error_msg="Please enter a valid path or allow creation"
    )

def debug_storage_info():
    """Debug function to show storage information"""
    print_step("Debug Storage Information")
    
    print("📋 Raw /proc/mounts output:")
    mounts = run("cat /proc/mounts | grep -E '(mergerfs|/mnt/)'", capture=True, check=False)
    if mounts:
        for line in mounts.splitlines():
            print(f"   {line}")
    else:
        print("   No relevant mounts found")
    
    print("\n📋 Raw fstab mergerfs entries:")
    fstab = run("grep mergerfs /etc/fstab", capture=True, check=False)
    if fstab:
        for line in fstab.splitlines():
            print(f"   {line}")
    else:
        print("   No mergerfs entries in fstab")
    
    print("\n📋 All /mnt/ mounts:")
    mnt_mounts = run("mount | grep /mnt/", capture=True, check=False)
    if mnt_mounts:
        for line in mnt_mounts.splitlines():
            print(f"   {line}")
    else:
        print("   No /mnt/ mounts found")

def view_storage_status():
    """Display current storage pool status"""
    print_step("Storage Pool Status")
    
    # Check for mergerfs mounts
    mounts_output = run("cat /proc/mounts", capture=True, check=False)
    mergerfs_mounts = [line for line in mounts_output.splitlines() if 'fuse.mergerfs' in line]
    
    if not mergerfs_mounts:
        print_warning("No mergerfs pools found")
        
        # Check for any mounted drives in /mnt
        print_info("Checking for individual mounted drives...")
        mount_output = run("mount | grep /mnt/", capture=True, check=False)
        if mount_output:
            print("� Individual mounted drives:")
            for line in mount_output.splitlines():
                print(f"   {line}")
        else:
            print_info("No drives mounted in /mnt/")
        return
    
    print("�📊 Active Storage Pools:")
    for mount in mergerfs_mounts:
        parts = mount.split()
        sources = parts[0]
        target = parts[1]
        
        print(f"\n🎯 Pool: {target}")
        print(f"   Sources: {sources.replace(':', ' + ')}")
        
        # Get usage info for the pool
        try:
            usage = run(f"df -h {target}", capture=True, check=False)
            usage_lines = usage.splitlines()
            if len(usage_lines) > 1:
                # Skip header line, get the data line
                data_line = usage_lines[1]
                parts = data_line.split()
                if len(parts) >= 6:
                    filesystem = parts[0]
                    size = parts[1]
                    used = parts[2]
                    avail = parts[3]
                    use_percent = parts[4]
                    mountpoint = parts[5]
                    print(f"   Total Size: {size}")
                    print(f"   Used: {used} ({use_percent})")
                    print(f"   Available: {avail}")
        except:
            print("   Could not get usage statistics")
        
        # List individual drives in the pool
        print(f"   📁 Individual drives:")
        source_paths = sources.split(':')
        
        # Map the source paths to actual devices with friendly names
        for i, source in enumerate(source_paths, 1):
            if source:
                try:
                    # Handle corrupted sources like "a1:b1:c1:d1"
                    if ':' in source and not source.startswith('/'):
                        print(f"      {i}. {source}: ⚠️  CORRUPTED SOURCE - needs repair")
                        continue
                    
                    # The source might be a short mount path, find the real device
                    mount_info = run(f"findmnt -n -o SOURCE,TARGET | grep '{source}'", capture=True, check=False)
                    if mount_info:
                        lines = mount_info.strip().splitlines()
                        for line in lines:
                            parts = line.split()
                            if len(parts) >= 2:
                                device = parts[0]
                                mount_path = parts[1]
                                if mount_path == source or mount_path.endswith(source):
                                    # Create friendly device name (e.g., /dev/sde1 → e1)
                                    friendly_name = device.replace('/dev/sd', '').replace('/dev/', '') if device.startswith('/dev/') else device
                                    
                                    # Get usage info for this specific mount
                                    usage = run(f"df -h {mount_path}", capture=True, check=False)
                                    usage_lines = usage.splitlines()
                                    if len(usage_lines) > 1:
                                        data_line = usage_lines[1]
                                        data_parts = data_line.split()
                                        if len(data_parts) >= 6:
                                            size = data_parts[1]
                                            used = data_parts[2]
                                            avail = data_parts[3]
                                            use_percent = data_parts[4]
                                            print(f"      {i}. {friendly_name} → {device}")
                                            print(f"         💿 {size} total, {used} used ({use_percent}), {avail} free")
                                        else:
                                            print(f"      {i}. {friendly_name} → {device} (mounted)")
                                    else:
                                        print(f"      {i}. {friendly_name} → {device} (mounted)")
                                    break
                        else:
                            print(f"      {i}. {source}: could not map to device")
                    else:
                        # Try to check if it's a /mnt/ path
                        full_path = source if source.startswith('/') else f"/mnt/{source}"
                        if Path(full_path).exists():
                            mount_info = run(f"findmnt -n -o SOURCE {full_path}", capture=True, check=False)
                            if mount_info:
                                device = mount_info.strip()
                                friendly_name = device.replace('/dev/sd', '').replace('/dev/', '') if device.startswith('/dev/') else device
                                print(f"      {i}. {friendly_name} → {device} (at {full_path})")
                            else:
                                print(f"      {i}. {source}: exists at {full_path} but not mounted")
                        else:
                            print(f"      {i}. {source}: ❌ path not found")
                except Exception as e:
                    print(f"      {i}. {source}: ❌ error mapping to device - {e}")
            else:
                print(f"      {i}. (empty source)")
        
        # Check for corrupted pool sources and offer repair
        if any(':' in s and not s.startswith('/') for s in source_paths):
            print(f"\n⚠️  DETECTED CORRUPTED POOL SOURCES!")
            print(f"   The pool contains malformed source paths that need repair.")
            print(f"   Use menu option 21 'Repair Storage Pool' to fix this.")
    
    # Show what's actually mounted in /mnt for reference
    print(f"\n📋 Current /mnt/ mounts for reference:")
    try:
        mnt_mounts = run("mount | grep '/mnt/'", capture=True, check=False)
        if mnt_mounts:
            for line in mnt_mounts.splitlines():
                print(f"   {line}")
        else:
            print("   No /mnt/ mounts found")
    except:
        print("   Could not get /mnt/ mount information")
    
    # Show overall system storage
    print(f"\n💿 System Storage Overview:")
    try:
        df_output = run("df -h | grep -E '^/dev/'", capture=True, check=False)
        if df_output:
            print("   All mounted filesystems:")
            for line in df_output.splitlines():
                print(f"      {line}")
    except:
        print("   Could not get system storage overview")
    
    # Show Docker volume usage if any
    print(f"\n🐳 Docker Volume Usage:")
    try:
        docker_usage = run("sudo docker system df", capture=True, check=False)
        if docker_usage:
            print(docker_usage)
    except:
        print("   Could not get Docker usage statistics")

def repair_storage_pool():
    """Repair corrupted storage pool by rebuilding mergerfs mount"""
    print_step("Storage Pool Repair")
    print("🔧 This will fix corrupted mergerfs pool sources")
    
    # Check for already mounted drives in /mnt/
    print_info("Scanning for mounted drives...")
    mounted_drives = []
    
    try:
        # Get mounted drives from df output
        df_output = run("df -h", capture=True, check=False)
        if df_output:
            for line in df_output.splitlines():
                if '/dev/sd' in line and '/mnt/sd' in line:
                    parts = line.split()
                    if len(parts) >= 6:
                        device = parts[0]
                        size = parts[1]
                        mount_point = parts[5]
                        
                        # Extract friendly name
                        device_name = device.split('/')[-1]  # Get sda1 from /dev/sda1
                        friendly_name = device_name.replace('sd', '').replace('1', '')
                        
                        mounted_drives.append({
                            'device': device,
                            'mount_point': mount_point,
                            'size': size,
                            'friendly_name': friendly_name
                        })
    except Exception as e:
        print_error(f"Error scanning drives: {e}")
        return
    
    if not mounted_drives:
        print_warning("No mounted drives found in /mnt/ to include in pool")
        return
    
    print(f"\n📋 Found {len(mounted_drives)} mounted drives:")
    for i, drive in enumerate(mounted_drives, 1):
        print(f"   {i}. {drive['friendly_name']} → {drive['device']} ({drive['size']}) at {drive['mount_point']}")
    
    if not get_yes_no_input(f"\n❓ Create pool with these {len(mounted_drives)} drives?", default=True):
        print_info("Pool creation cancelled")
        return
    
    try:
        # Unmount existing corrupted pool if it exists
        print_info("Unmounting any existing pool...")
        run("sudo umount /mnt/pool", check=False)
        
        # Create pool directory
        run("sudo mkdir -p /mnt/pool")
        
        # Clear any existing content
        run("sudo rm -rf /mnt/pool/* 2>/dev/null", check=False)
        
        # Create new pool with all valid mount points
        mount_points = [drive['mount_point'] for drive in mounted_drives]
        sources = ':'.join(mount_points)
        
        print_info(f"Creating pool: {sources.replace(':', ' + ')}")
        
        cmd = f"sudo mergerfs {sources} /mnt/pool -o defaults,allow_other,use_ino,cache.files=partial,dropcacheonclose=true,category.create=mfs,nonempty"
        run(cmd)
        
        # Update fstab using original as base
        print_info("Updating /etc/fstab...")
        
        # Start with original fstab
        original_fstab = run("cat /etc/fstab.original", capture=True, check=False)
        if not original_fstab:
            print_warning("No /etc/fstab.original found, using current fstab")
            original_fstab = run("cat /etc/fstab", capture=True)
        
        updated_fstab = original_fstab.splitlines()
        
        # Add individual drive entries
        for drive in mounted_drives:
            uuid = run(f"sudo blkid -s UUID -o value {drive['device']}", capture=True, check=False)
            if uuid:
                fstab_entry = f"UUID={uuid} {drive['mount_point']} ext4 defaults,nofail 0 0"
                updated_fstab.append(fstab_entry)
        
        # Add mergerfs pool entry
        new_fstab_entry = f"{sources} /mnt/pool fuse.mergerfs defaults,allow_other,use_ino,cache.files=partial,dropcacheonclose=true,category.create=mfs,nonempty 0 0"
        updated_fstab.append(new_fstab_entry)
        
        # Write updated fstab
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_fstab:
            tmp_fstab.write('\n'.join(updated_fstab) + '\n')
            tmp_fstab_path = tmp_fstab.name
        
        run(f"sudo cp {tmp_fstab_path} /etc/fstab")
        os.unlink(tmp_fstab_path)
        
        # Reload systemd
        run("sudo systemctl daemon-reload", check=False)
        
        print_success("🎉 Storage pool successfully created!")
        
        # Show the new pool status
        pool_usage = run("df -h /mnt/pool", capture=True, check=False)
        if pool_usage:
            print(f"\n📊 Pool status:")
            for line in pool_usage.splitlines():
                if '/mnt/pool' in line:
                    print(f"   {line}")
        
        print(f"\n✅ Pool includes drives:")
        for drive in mounted_drives:
            print(f"   • {drive['friendly_name']} ({drive['size']})")
            
    except Exception as e:
        print_error(f"Failed to create storage pool: {e}")

def manual_drive_recovery():
    """Step-by-step manual recovery: mount each drive individually, then create pool"""
    print_step("Manual Drive Recovery")
    print("🛠️  Step-by-step recovery: mount drives individually, then create pool")
    
    # Step 1: Show current unmounted drives
    print_info("Step 1: Scanning for unmounted drives...")
    try:
        # Get all partitions from lsblk
        lsblk_output = run("lsblk -rno NAME,SIZE,TYPE,MOUNTPOINT", capture=True, check=True)
        unmounted_drives = []
        
        if lsblk_output:
            for line in lsblk_output.splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    name, size, dtype = parts[0], parts[1], parts[2]
                    mountpoint = parts[3] if len(parts) > 3 and parts[3].strip() else None
                    
                    # Look for unmounted storage drive partitions (sda1, sdb1, etc. but not nvme)
                    if (dtype == 'part' and 
                        not mountpoint and 
                        name.startswith('sd') and 
                        name.endswith('1') and
                        name in ['sda1', 'sdb1', 'sdc1', 'sdd1', 'sde1']):
                        
                        device_path = f"/dev/{name}"
                        
                        # Try to detect filesystem with blkid
                        detected_fstype = 'ext4'  # default fallback
                        try:
                            blkid_output = run(f"sudo blkid {device_path}", capture=True, check=False)
                            if blkid_output:
                                if 'TYPE="ext4"' in blkid_output:
                                    detected_fstype = 'ext4'
                                elif 'TYPE="xfs"' in blkid_output:
                                    detected_fstype = 'xfs'
                                elif 'TYPE="btrfs"' in blkid_output:
                                    detected_fstype = 'btrfs'
                                print_info(f"Detected {name}: {detected_fstype} filesystem")
                            else:
                                print_warning(f"Could not detect filesystem for {name}, assuming ext4")
                        except Exception as e:
                            print_warning(f"blkid failed for {name}: {e}, assuming ext4")
                        
                        unmounted_drives.append({
                            'device': device_path,
                            'name': name,
                            'size': size,
                            'fstype': detected_fstype,
                            'friendly_name': name.replace('sd', '').replace('1', ''),
                            'mount_point': f"/mnt/{name.rstrip('1234567890')}"  # Remove partition numbers
                        })
        
        if not unmounted_drives:
            print_warning("No unmounted drives found")
            print("📋 Let's check what we have:")
            # Show all partitions for debugging
            all_parts = run("lsblk | grep 'part'", capture=True, check=False)
            if all_parts:
                print("   All partitions:")
                for line in all_parts.splitlines():
                    print(f"      {line}")
            
            # Also try to manually check each expected drive
            print("\n🔍 Manual check of expected drives:")
            expected_drives = ['sda1', 'sdb1', 'sdc1', 'sdd1', 'sde1']
            for drive_name in expected_drives:
                device_path = f"/dev/{drive_name}"
                try:
                    # Check if device exists
                    ls_result = run(f"ls -la {device_path}", capture=True, check=False)
                    if ls_result:
                        print(f"   ✅ {device_path} exists")
                        
                        # Check if mounted
                        mount_check = run(f"mount | grep {device_path}", capture=True, check=False)
                        if mount_check:
                            print(f"      � Mounted: {mount_check.strip()}")
                        else:
                            print(f"      📀 Not mounted - available for recovery")
                    else:
                        print(f"   ❌ {device_path} not found")
                except:
                    print(f"   ❌ Error checking {device_path}")
            return
        
        print(f"📋 Found {len(unmounted_drives)} unmounted drives:")
        for i, drive in enumerate(unmounted_drives, 1):
            print(f"   {i}. {drive['friendly_name']} → {drive['device']} ({drive['size']}, {drive['fstype']})")
            print(f"      Will mount at: {drive['mount_point']}")
        
        if not get_yes_no_input(f"\n❓ Proceed with mounting these {len(unmounted_drives)} drives?", default=True):
            print_info("Recovery cancelled")
            return
        
        # Step 2: Mount each drive individually
        print_info("Step 2: Mounting each drive individually...")
        mounted_drives = []
        
        for drive in unmounted_drives:
            try:
                print_info(f"Mounting {drive['device']} at {drive['mount_point']}")
                
                # Create mount point directory
                run(f"sudo mkdir -p {drive['mount_point']}")
                
                # Mount the drive
                run(f"sudo mount {drive['device']} {drive['mount_point']}")
                
                # Set proper ownership
                run(f"sudo chown 1000:1000 {drive['mount_point']}")
                
                # Verify mount
                mount_check = run(f"df -h {drive['mount_point']}", capture=True, check=False)
                if mount_check and drive['mount_point'] in mount_check:
                    mounted_drives.append(drive)
                    print_success(f"✅ Successfully mounted {drive['friendly_name']} at {drive['mount_point']}")
                else:
                    print_error(f"❌ Failed to verify mount for {drive['device']}")
                
            except Exception as e:
                print_error(f"❌ Failed to mount {drive['device']}: {e}")
                continue
        
        if not mounted_drives:
            print_error("No drives were successfully mounted")
            return
        
        print_success(f"✅ Successfully mounted {len(mounted_drives)} drives")
        
        # Step 3: Create pool mount point
        print_info("Step 3: Creating pool mount point...")
        try:
            run("sudo mkdir -p /mnt/pool", check=False)  # Don't fail if directory exists
            print_success("✅ Pool mount point ready at /mnt/pool")
        except Exception as e:
            print_error(f"❌ Failed to create /mnt/pool: {e}")
            return
        
        # Step 4: Create mergerfs pool
        print_info("Step 4: Creating mergerfs storage pool...")
        try:
            # Unmount any existing corrupted pool first
            run("sudo umount /mnt/pool", check=False)
            
            # Clear the pool directory if it has content
            pool_content = run("ls -la /mnt/pool", capture=True, check=False)
            if pool_content and len(pool_content.strip().splitlines()) > 3:  # More than just . and ..
                print_info("Clearing existing pool directory content...")
                run("sudo rm -rf /mnt/pool/*", check=False)
                run("sudo rm -rf /mnt/pool/.*", check=False)  # Remove hidden files too
            
            # Create source list for mergerfs
            mount_points = [drive['mount_point'] for drive in mounted_drives]
            sources = ':'.join(mount_points)
            
            print_info(f"Pool sources: {sources.replace(':', ' + ')}")
            
            # Create mergerfs command with nonempty option
            cmd = f"sudo mergerfs {sources} /mnt/pool -o defaults,allow_other,use_ino,cache.files=partial,dropcacheonclose=true,category.create=mfs,nonempty"
            run(cmd)
            
            # Verify pool creation
            pool_check = run("df -h /mnt/pool", capture=True, check=False)
            if pool_check and "/mnt/pool" in pool_check:
                print_success("✅ Storage pool created successfully")
                
                # Show pool status
                for line in pool_check.splitlines():
                    if "/mnt/pool" in line:
                        print(f"   📊 {line}")
            else:
                print_error("❌ Failed to verify pool creation")
                return
                
        except Exception as e:
            print_error(f"❌ Failed to create storage pool: {e}")
            return
        
        # Step 5: Update /etc/fstab
        print_info("Step 5: Updating /etc/fstab for persistent mounting...")
        try:
            # Read current fstab
            fstab_content = run("cat /etc/fstab", capture=True)
            updated_fstab = []
            
            # Remove old entries for these mount points and mergerfs
            for line in fstab_content.splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    # Skip old entries for our mount points and mergerfs pool
                    skip_line = False
                    for drive in mounted_drives:
                        if drive['mount_point'] in line or (drive['device'] in line and drive['mount_point'] in line):
                            skip_line = True
                            break
                    if '/mnt/pool' in line and 'fuse.mergerfs' in line:
                        skip_line = True
                    
                    if not skip_line:
                        updated_fstab.append(line)
                else:
                    updated_fstab.append(line)
            
            # Add new entries for each individual drive
            for drive in mounted_drives:
                # Get UUID for persistent mounting
                uuid = run(f"sudo blkid -s UUID -o value {drive['device']}", capture=True, check=False)
                if uuid:
                    fstab_entry = f"UUID={uuid} {drive['mount_point']} {drive['fstype']} defaults,nofail 0 0"
                    updated_fstab.append(fstab_entry)
                    print_info(f"Added fstab entry for {drive['friendly_name']}: {drive['mount_point']}")
                else:
                    print_warning(f"Could not get UUID for {drive['device']}")
            
            # Add mergerfs pool entry
            mount_points = [drive['mount_point'] for drive in mounted_drives]
            sources = ':'.join(mount_points)
            mergerfs_entry = f"{sources} /mnt/pool fuse.mergerfs defaults,allow_other,use_ino,cache.files=partial,dropcacheonclose=true,category.create=mfs 0 0"
            updated_fstab.append(mergerfs_entry)
            
            # Write updated fstab
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_fstab:
                tmp_fstab.write('\n'.join(updated_fstab) + '\n')
                tmp_fstab_path = tmp_fstab.name
            
            run(f"sudo cp {tmp_fstab_path} /etc/fstab")
            os.unlink(tmp_fstab_path)
            
            print_success("✅ Updated /etc/fstab for persistent mounting")
            
        except Exception as e:
            print_error(f"❌ Failed to update /etc/fstab: {e}")
            print_warning("Drives are mounted but may not survive reboot")
        
        # Step 6: Final verification and summary
        print_info("Step 6: Final verification...")
        try:
            # Show all mounted drives
            print("\n" + "="*80)
            print("🎉 RECOVERY COMPLETE!")
            print("="*80)
            
            print(f"\n📁 Individual drives mounted:")
            for drive in mounted_drives:
                usage = run(f"df -h {drive['mount_point']}", capture=True, check=False)
                if usage:
                    usage_lines = usage.splitlines()
                    if len(usage_lines) > 1:
                        usage_parts = usage_lines[1].split()
                        if len(usage_parts) >= 6:
                            size = usage_parts[1]
                            used = usage_parts[2]
                            avail = usage_parts[3]
                            use_pct = usage_parts[4]
                            print(f"   • {drive['friendly_name']} → {drive['device']} at {drive['mount_point']}")
                            print(f"     💿 {size} total, {used} used ({use_pct}), {avail} available")
            
            # Show pool status
            pool_usage = run("df -h /mnt/pool", capture=True, check=False)
            if pool_usage:
                print(f"\n🎯 Storage Pool:")
                for line in pool_usage.splitlines():
                    if "/mnt/pool" in line:
                        parts = line.split()
                        if len(parts) >= 6:
                            size = parts[1]
                            used = parts[2]
                            avail = parts[3]
                            use_pct = parts[4]
                            print(f"   📊 Combined Pool: {size} total, {used} used ({use_pct}), {avail} available")
            
            print(f"\n✅ Recovery Summary:")
            print(f"   • {len(mounted_drives)} drives successfully mounted")
            print(f"   • Storage pool created at /mnt/pool")
            print(f"   • /etc/fstab updated for persistent mounting")
            print(f"   • All data preserved and accessible")
            
            print(f"\n💡 Next steps:")
            print(f"   • Verify your data is accessible in /mnt/pool")
            print(f"   • Test reboot to ensure mounts persist")
            print(f"   • Use option 9 to view storage status anytime")
            
        except Exception as e:
            print_error(f"Error during final verification: {e}")
            
    except Exception as e:
        print_error(f"Error during drive recovery: {e}")

def recover_corrupted_pool():
    """Non-destructive recovery for completely broken storage pools"""
    print_step("Storage Pool Recovery")
    print("🛠️  This will safely recover your drives from a corrupted pool")
    print("📊 First, let's see what we're working with...")
    
    # Check current disk status
    try:
        print_info("Current disk status:")
        df_output = run("df -h", capture=True, check=False)
        if df_output:
            relevant_lines = []
            for line in df_output.splitlines():
                if '/dev/sd' in line or '/mnt/' in line or 'fuse.mergerfs' in line:
                    relevant_lines.append(line)
            
            if relevant_lines:
                print("📋 Current mounts:")
                for line in relevant_lines:
                    print(f"   {line}")
            else:
                print("   No relevant mounts found")
    except:
        print_warning("Could not get disk status")
    
    # Check for existing fstab entries
    print_info("Checking /etc/fstab for drive configurations...")
    try:
        fstab_content = run("cat /etc/fstab", capture=True, check=False)
        drive_entries = []
        mergerfs_entries = []
        
        for line in fstab_content.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                if '/dev/sd' in line or 'UUID=' in line:
                    if '/mnt/' in line and 'fuse.mergerfs' not in line:
                        drive_entries.append(line)
                elif 'fuse.mergerfs' in line:
                    mergerfs_entries.append(line)
        
        if drive_entries:
            print(f"📁 Found {len(drive_entries)} drive entries in fstab:")
            for i, entry in enumerate(drive_entries, 1):
                print(f"   {i}. {entry}")
        
        if mergerfs_entries:
            print(f"🔗 Found mergerfs entries:")
            for entry in mergerfs_entries:
                print(f"   {entry}")
    except:
        print_warning("Could not read /etc/fstab")
    
    # Detect available block devices
    print_info("Scanning for available block devices...")
    try:
        lsblk_output = run("lsblk -rno NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE", capture=True, check=False)
        available_partitions = []
        
        if lsblk_output:
            for line in lsblk_output.splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    name, size, dtype, mountpoint = parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else ""
                    fstype = parts[4] if len(parts) > 4 else ""
                    
                    # Look for unmounted partitions with filesystems
                    if dtype == 'part' and fstype in ['ext4', 'xfs', 'btrfs'] and not mountpoint:
                        available_partitions.append({
                            'device': f"/dev/{name}",
                            'name': name,
                            'size': size,
                            'fstype': fstype,
                            'friendly_name': name.replace('sd', '').replace('1', '')
                        })
        
        if available_partitions:
            print(f"🔍 Found {len(available_partitions)} unmounted drives with data:")
            for i, part in enumerate(available_partitions, 1):
                print(f"   {i}. {part['friendly_name']} → {part['device']} ({part['size']}, {part['fstype']})")
            
            if get_yes_no_input(f"\n❓ Mount these {len(available_partitions)} drives and recreate pool?", default=True):
                # Mount each drive individually
                mounted_drives = []
                
                for part in available_partitions:
                    try:
                        mount_point = f"/mnt/{part['name'].rstrip('1234567890')}"  # Remove partition numbers
                        print_info(f"Mounting {part['device']} at {mount_point}")
                        
                        # Create mount point
                        run(f"sudo mkdir -p {mount_point}")
                        
                        # Mount the drive
                        run(f"sudo mount {part['device']} {mount_point}")
                        
                        # Set ownership
                        run(f"sudo chown 1000:1000 {mount_point}")
                        
                        mounted_drives.append({
                            'device': part['device'],
                            'mount_point': mount_point,
                            'size': part['size'],
                            'friendly_name': part['friendly_name']
                        })
                        
                        print_success(f"✅ Mounted {part['friendly_name']} at {mount_point}")
                        
                    except Exception as e:
                        print_error(f"Failed to mount {part['device']}: {e}")
                        continue
                
                if mounted_drives:
                    # Create the new pool
                    print_info("Creating new storage pool...")
                    mount_points = [drive['mount_point'] for drive in mounted_drives]
                    sources = ':'.join(mount_points)
                    
                    try:
                        # Unmount any existing corrupted pool
                        run("sudo umount /mnt/pool", check=False)
                        
                        # Create pool directory
                        run("sudo mkdir -p /mnt/pool")
                        
                        # Create mergerfs pool
                        cmd = f"sudo mergerfs {sources} /mnt/pool -o defaults,allow_other,use_ino,cache.files=partial,dropcacheonclose=true,category.create=mfs"
                        run(cmd)
                        
                        print_success("🎉 Storage pool successfully recreated!")
                        
                        # Update fstab
                        print_info("Updating /etc/fstab...")
                        fstab_content = run("cat /etc/fstab", capture=True)
                        updated_fstab = []
                        
                        # Remove old mergerfs entries
                        for line in fstab_content.splitlines():
                            if not ('fuse.mergerfs' in line and '/mnt/pool' in line):
                                updated_fstab.append(line)
                        
                        # Add individual drive entries
                        for drive in mounted_drives:
                            uuid = run(f"sudo blkid -s UUID -o value {drive['device']}", capture=True, check=False)
                            if uuid:
                                fstype = run(f"sudo blkid -s TYPE -o value {drive['device']}", capture=True, check=False) or "ext4"
                                fstab_entry = f"UUID={uuid} {drive['mount_point']} {fstype} defaults,nofail 0 0"
                                updated_fstab.append(fstab_entry)
                        
                        # Add new mergerfs entry
                        new_fstab_entry = f"{sources} /mnt/pool fuse.mergerfs defaults,allow_other,use_ino,cache.files=partial,dropcacheonclose=true,category.create=mfs 0 0"
                        updated_fstab.append(new_fstab_entry)
                        
                        # Write updated fstab
                        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_fstab:
                            tmp_fstab.write('\n'.join(updated_fstab) + '\n')
                            tmp_fstab_path = tmp_fstab.name
                        
                        run(f"sudo cp {tmp_fstab_path} /etc/fstab")
                        os.unlink(tmp_fstab_path)
                        
                        # Show results
                        pool_usage = run("df -h /mnt/pool", capture=True, check=False)
                        if pool_usage:
                            print(f"\n📊 New pool status:")
                            for line in pool_usage.splitlines():
                                if '/mnt/pool' in line:
                                    print(f"   {line}")
                        
                        print(f"\n✅ Recovered drives:")
                        for drive in mounted_drives:
                            print(f"   • {drive['friendly_name']} → {drive['device']} ({drive['size']})")
                        
                    except Exception as e:
                        print_error(f"Failed to create pool: {e}")
                else:
                    print_error("No drives were successfully mounted")
            else:
                print_info("Recovery cancelled")
        else:
            print_warning("No unmounted drives with data found to recover")
            print("💡 Your drives might be:")
            print("   • Already mounted somewhere else")
            print("   • Need to be unmounted from corrupted pool first")
            print("   • Corrupted and need filesystem repair")
            
    except Exception as e:
        print_error(f"Error during recovery scan: {e}")

def select_services_to_install():
    """Interactive service selection menu"""
    service_descriptions = {
        'jellyfin': '📺 Media server (like Plex) for streaming movies/TV shows',
        'radarr': '🎬 Movie collection manager and automatic downloader',
        'sonarr': '📺 TV show collection manager and automatic downloader', 
        'jellyseerr': '📋 Request management system for Jellyfin',
        'sabnzbd': '📦 Usenet downloader and processor',
        'tdarr_server': '🎞️  Video transcoding server (main controller)',
        'tdarr_node': '⚙️  Video transcoding worker node',
        'watchtower': '🔄 Automatic container updates',
        'portainer': '🐳 Docker management web interface'
    }
    
    print("\n" + "="*80)
    print("🐳 SERVICE SELECTION")
    print("="*80)
    print("Select which services you want to install:")
    print()
    
    # Display services with numbers
    service_list = list(service_descriptions.keys())
    for i, service in enumerate(service_list, 1):
        desc = service_descriptions[service]
        print(f" {i:2}. {desc}")
    
    print()
    print("📝 Selection Options:")
    print("   • Enter numbers separated by commas (e.g., 1,2,5)")
    print("   • Enter 'a' for ALL services")
    print("   • Enter 'r' for RECOMMENDED services (Jellyfin, Radarr, Sonarr, Jellyseerr)")
    print("   • Enter 'q' to cancel")
    
    while True:
        choice = input('\n🎯 Select services: ').strip().lower()
        
        if choice == 'q':
            return None
        elif choice == 'a':
            if get_yes_no_input("❓ Install ALL services?", default=False):
                return service_list
            continue
        elif choice == 'r':
            recommended = ['jellyfin', 'radarr', 'sonarr', 'jellyseerr']
            print("📋 Recommended services:")
            for service in recommended:
                print(f"   • {service} - {service_descriptions[service]}")
            if get_yes_no_input("❓ Install recommended services?", default=True):
                return recommended
            continue
        else:
            try:
                service_nums = [int(x.strip()) for x in choice.split(',')]
                invalid_nums = [n for n in service_nums if n < 1 or n > len(service_list)]
                if invalid_nums:
                    print_error(f"Invalid service numbers: {invalid_nums}")
                    continue
                
                selected_services = [service_list[n-1] for n in service_nums]
                
                print(f"\n📋 Selected services:")
                for service in selected_services:
                    print(f"   • {service} - {service_descriptions[service]}")
                
                if get_yes_no_input("❓ Proceed with these services?", default=True):
                    return selected_services
                    
            except ValueError:
                print_error("Please enter valid numbers separated by commas.")
                continue

def install_services_with_selection(media_root, gpu_enabled, selected_services=None):
    """Install only selected services"""
    if selected_services is None:
        selected_services = select_services_to_install()
        if selected_services is None:
            print_info("Service installation cancelled.")
            return
    
    paths = get_paths(media_root)
    templates = get_templates(paths, gpu_enabled)
    existing = run("sudo docker ps -a --format '{{.Names}}'", capture=True).splitlines()
    
    print(f"\n🐳 Installing {len(selected_services)} selected services...")
    
    # Filter templates to only include selected services
    filtered_templates = {k: v for k, v in templates.items() if k in selected_services}
    
    # Use the existing install logic but with filtered templates
    to_run = list(filtered_templates.keys())
    
    # Gather shared prompts if needed
    tdarr_ip, tdarr_port = None, None
    tdarr_node_ip, tdarr_node_port = None, None
    watchtower_args = None
    
    if any(s in to_run for s in ('tdarr_node', 'tdarr_server')):
        print("Select the IP for Tdarr Server to bind to:")
        iface_map = list_local_ips_shell()
        ip_choice = input(f"Enter number or custom IP [{get_local_ip()}]: ").strip()
        if ip_choice in iface_map:
            tdarr_ip = iface_map[ip_choice]
        elif ip_choice:
            tdarr_ip = ip_choice
        else:
            tdarr_ip = get_local_ip()
        tdarr_port = input("Enter Tdarr server port [8266]: ").strip() or "8266"
        tdarr_node_ip = tdarr_ip
        tdarr_node_port = tdarr_port
        if 'tdarr_node' in to_run:
            use_external = input("Is the Tdarr server external? (y/n): ").strip().lower() == 'y'
            if use_external:
                tdarr_node_ip = input("Enter external Tdarr server IP: ").strip()
                tdarr_node_port = input("Enter external Tdarr server port [8266]: ").strip() or "8266"
    
    if 'watchtower' in to_run:
        frm = input("Watchtower email FROM: ")
        to = input("Watchtower email TO: ")
        srv = input("Watchtower SMTP server: ")
        prt = input("Watchtower SMTP port [587]: ").strip() or "587"
        usr = frm
        pwd = getpass.getpass("Watchtower SMTP password: ")
        watchtower_args = (frm, to, srv, prt, usr, pwd)

    # Install selected services
    for svc in to_run:
        if svc in existing:
            print_info(f"Reinstalling {svc}...")
            run(f"sudo docker stop {svc}")
            run(f"sudo docker rm {svc}")
        
        if svc == 'tdarr_server':
            cmd = filtered_templates[svc](tdarr_ip, tdarr_port)
        elif svc == 'tdarr_node':
            cmd = filtered_templates[svc](tdarr_node_ip, tdarr_node_port)
        elif svc == 'watchtower':
            cmd = filtered_templates[svc](*watchtower_args)
        else:
            cmd = filtered_templates[svc]()
        
        print_step(f"Installing {svc}...")
        run(cmd)
    
    print_success(f'Successfully installed {len(selected_services)} services!')
    
    # Show access URLs for installed services
    local_ip = get_local_ip()
    service_urls = {
        'jellyfin': f"http://{local_ip}:8096",
        'radarr': f"http://{local_ip}:7878",
        'sonarr': f"http://{local_ip}:8989",
        'jellyseerr': f"http://{local_ip}:5055",
        'sabnzbd': f"http://{local_ip}:8080",
        'tdarr_server': f"http://{local_ip}:8265",
        'portainer': f"https://{local_ip}:9443"
    }
    
    print("\n🌐 Service Access URLs:")
    for service in selected_services:
        if service in service_urls:
            print(f"  • {service.title()}: {service_urls[service]}")

def run_custom_setup():
    """Run setup with custom service selection"""
    print_step("Custom Media Server Setup")
    
    if platform.system().lower() != "linux":
        print_warning("This script was designed for Linux systems.")
        if not get_yes_no_input("❓ Continue anyway?", default=False):
            print_info("Setup cancelled.")
            return
    
    # Get what components they want to set up
    print("\n📝 Setup Components:")
    print("Select which parts of the setup you want to configure:")
    
    setup_docker = get_yes_no_input("1. 🐳 Install Docker & dependencies?", default=True)
    setup_gpu = get_yes_no_input("2. 🎮 Configure GPU acceleration?", default=True)
    setup_storage = get_yes_no_input("3. 💾 Configure storage pool?", default=True)
    setup_directories = get_yes_no_input("4. 📁 Create config directories?", default=True)
    setup_vpn = get_yes_no_input("5. 🔐 Install PIA VPN?", default=False)
    setup_services = get_yes_no_input("6. 🐳 Install services?", default=True)
    
    step_num = 1
    total_steps = sum([setup_docker, setup_gpu, setup_storage, setup_directories, setup_vpn, setup_services])
    
    media_root = "/mnt/pool"  # Default
    gpu_enabled = False
    
    if setup_docker:
        print_step("Installing Docker & Dependencies", step_num, total_steps)
        install_docker()
        step_num += 1
    
    if setup_gpu:
        print_step("GPU Configuration", step_num, total_steps)
        gpu_enabled = True
        setup_nvidia()
        step_num += 1
    
    if setup_storage:
        print_step("Storage Pool Setup", step_num, total_steps)
        media_root = get_validated_input(
            "📁 Enter media pool mount point [/mnt/pool]",
            required=False
        ) or "/mnt/pool"
        setup_storage_pool(media_root)
        step_num += 1
    
    if setup_directories:
        print_step("Directory Configuration", step_num, total_steps)
        ensure_config_directories()
        step_num += 1
    
    if setup_vpn:
        print_step("VPN Setup", step_num, total_steps)
        setup_pia()
        step_num += 1
    
    if setup_services:
        print_step("Service Installation", step_num, total_steps)
        install_services_with_selection(media_root, gpu_enabled)
    
    print("\n" + "="*80)
    print_success("🎉 CUSTOM SETUP COMPLETE!")
    print("="*80)

def main():
    print("\n" + "="*80)
    print("🎬 MEDIA SERVER SETUP WIZARD")
    print("="*80)
    print("Welcome! This script will help you set up a complete media server.")
    print("Features: Jellyfin, Radarr, Sonarr, GPU transcoding, VPN, and more!")
    print("="*80)
    
    # Check if this is first run or menu mode
    if len(sys.argv) > 1 and sys.argv[1] == '--menu':
        main_menu()
        return
    
    # Ask user what they want to do
    print("\n📝 What would you like to do?")
    print("  1. Complete setup wizard (full setup, all services)")
    print("  2. Custom setup wizard (choose components & services)")
    print("  3. Quick access menu (for specific tasks)")
    
    while True:
        choice = input("\n🎯 Select option (1-3): ").strip()
        if choice == '1':
            run_full_setup()
            break
        elif choice == '2':
            run_custom_setup()
            break
        elif choice == '3':
            main_menu()
            break
        else:
            print_error("Please enter 1, 2, or 3")

def main_menu():
    """Main interactive menu system"""
    while True:
        show_main_menu()
        choice = input("\n🎯 Select option (0-23): ").strip()
        
        try:
            if choice == '0':
                print_info("Goodbye! 👋")
                break
            elif choice == '1':
                run_full_setup()
            elif choice == '2':
                run_custom_setup()
            elif choice == '3':
                install_docker()
            elif choice == '4':
                setup_nvidia()
            elif choice == '5':
                setup_pia()
            elif choice == '6':
                media_root = get_validated_input("📁 Enter media pool mount point [/mnt/pool]", required=False) or "/mnt/pool"
                setup_storage_pool(media_root)
            elif choice == '7':
                media_root = get_media_root()
                add_drive_to_pool(media_root)
            elif choice == '8':
                media_root = get_media_root()
                remove_drives_from_pool(media_root)
            elif choice == '9':
                view_storage_status()
            elif choice == '10':
                media_root = get_media_root()
                gpu_enabled = get_yes_no_input('🎮 Enable GPU acceleration?', default=True)
                install_services_with_selection(media_root, gpu_enabled)
            elif choice == '11':
                run("sudo docker start $(sudo docker ps -aq)", check=False)
                print_success("All services started")
            elif choice == '12':
                run("sudo docker stop $(sudo docker ps -aq)", check=False)
                print_success("All services stopped")
            elif choice == '13':
                run("sudo docker restart $(sudo docker ps -aq)", check=False)
                print_success("All services restarted")
            elif choice == '14':
                manage_services()
            elif choice == '15':
                remove_services()
            elif choice == '16':
                run("sudo docker pull $(sudo docker images --format '{{.Repository}}:{{.Tag}}' | grep -v '<none>')", check=False)
                print_success("Containers updated")
            elif choice == '17':
                run("sudo docker system prune -af", check=False)
                print_success("Docker cleanup complete")
            elif choice == '18':
                show_system_info()
            elif choice == '19':
                ensure_config_directories()
            elif choice == '20':
                debug_storage_info()
            elif choice == '21':
                repair_storage_pool()
            elif choice == '22':
                recover_corrupted_pool()
            elif choice == '23':
                manual_drive_recovery()
            else:
                print_error("Invalid option. Please enter 0-23.")
                
        except KeyboardInterrupt:
            print("\n\n❌ Operation cancelled.")
        except Exception as e:
            print_error(f"An error occurred: {e}")
        
        if choice != '0':
            input("\n⏸️  Press Enter to continue...")

def manage_services():
    """Service management submenu"""
    print_step("Service Status")
    run("sudo docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'", check=False)

def remove_services():
    """Remove selected services"""
    services = ['jellyfin', 'radarr', 'sonarr', 'jellyseerr', 'sabnzbd', 
                'tdarr_server', 'tdarr_node', 'watchtower', 'portainer']
    
    print("\n🗑️  REMOVE SERVICES")
    print("Available services:")
    for i, svc in enumerate(services, 1):
        print(f"  {i}. {svc}")
    
    selection = input("\nEnter service numbers to remove (e.g., 1,2,3) or 'q' to cancel: ").strip()
    
    if selection.lower() == 'q':
        print_info("Service removal cancelled.")
        return
    
    try:
        indices = [int(x.strip()) for x in selection.split(',')]
        to_remove = [services[i-1] for i in indices if 1 <= i <= len(services)]
        
        if to_remove and get_yes_no_input(f"❓ Remove services: {', '.join(to_remove)}?", default=False):
            for svc in to_remove:
                print_info(f"Removing {svc}...")
                run(f"sudo docker stop {svc}", check=False)
                run(f"sudo docker rm {svc}", check=False)
            print_success("Services removed successfully!")
    except:
        print_error("Invalid selection")

def setup_nvidia():
    """Standalone NVIDIA setup"""
    print_step("GPU Configuration")
    
    if not check_nvidia_driver():
        print_info("NVIDIA driver not detected. Installing...")
        install_nvidia_driver()
    else:
        print_success("NVIDIA driver detected!")
        
    install_nvidia_container_toolkit()
    cv = detect_cuda_version() or get_validated_input(
        "🎯 Enter CUDA version (e.g., 12.1.0)",
        validator=lambda x: len(x.split('.')) >= 2,
        error_msg="Please enter a valid CUDA version (e.g., 12.1.0)"
    )
    test_docker_gpu(cv)
    
    if get_yes_no_input('🔧 Download and install NVIDIA transcoding patch?', default=False):
        install_nvidia_patch()

def setup_pia():
    """Standalone PIA VPN setup"""
    print_step("VPN Setup")
    install_pia()
    login_pia()

def show_system_info():
    """Display system information"""
    print_step("System Information")
    
    print("🖥️  System:")
    run("uname -a", check=False)
    
    print("\n💾 Memory:")
    run("free -h", check=False)
    
    print("\n💿 Storage:")
    run("df -h", check=False)
    
    print("\n🐳 Docker:")
    run("sudo docker version", check=False)
    run("sudo docker ps", check=False)
    
    print("\n🎮 GPU:")
    run("nvidia-smi", check=False)

def run_full_setup():
    """Run the complete setup wizard"""
    if platform.system().lower() != "linux":
        print_warning("This script was designed for Linux systems.")
        print("Detected features that may not work on your OS:")
        print("  • Storage pool setup with mergerfs")
        print("  • NVIDIA GPU acceleration")
        print("  • PIA VPN integration")
        print("  • Package management commands")
        
        if not get_yes_no_input("❓ Continue anyway?", default=False):
            print_info("Setup cancelled. Consider running this on a Linux system.")
            return
    
    print_step("Initial System Setup", 1, 6)
    install_docker()
    
    print_step("GPU Configuration", 2, 6)
    gpu_enabled = get_yes_no_input('🎮 Enable GPU acceleration for video transcoding?', default=True)
    
    if gpu_enabled:
        setup_nvidia()
    
    print_step("Storage Pool Setup", 3, 6)
    
    # Check if pool already exists
    existing_pool = Path("/mnt/pool")  # Default location, could be made configurable
    has_existing_pool = existing_pool.exists() and is_mount_point(existing_pool)
    
    if has_existing_pool:
        print_info(f"Existing storage pool detected at /mnt/pool")
        
        if get_yes_no_input('💾 Do you want to manage your storage pool?', default=True):
            print("\n📝 Storage Pool Options:")
            print("  1. Add drives to existing pool")
            print("  2. Remove drives from existing pool")
            print("  3. Set up completely new pool") 
            print("  4. Use existing pool as-is")
            
            while True:
                choice = input("\n🎯 Select option (1-4): ").strip()
                if choice == '1':
                    add_drive_to_pool("/mnt/pool")
                    media_root = "/mnt/pool"
                    break
                elif choice == '2':
                    remove_drives_from_pool("/mnt/pool")
                    media_root = "/mnt/pool"
                    break
                elif choice == '3':
                    media_root = get_validated_input(
                        "📁 Enter media pool mount point [/mnt/pool]",
                        required=False
                    ) or "/mnt/pool"
                    setup_storage_pool(media_root)
                    break
                elif choice == '4':
                    media_root = "/mnt/pool"
                    print_info("Using existing storage pool")
                    break
                else:
                    print_error("Please enter 1, 2, 3, or 4")
        else:
            media_root = "/mnt/pool"
    else:
        if get_yes_no_input('💾 Setup media storage pool with mergerfs?', default=True):
            media_root = get_validated_input(
                "📁 Enter media pool mount point [/mnt/pool]",
                required=False
            ) or "/mnt/pool"
            setup_storage_pool(media_root)
        else:
            media_root = get_validated_input(
                "📁 Enter existing media mount point",
                validator=lambda x: Path(x).exists(),
                error_msg="Directory does not exist. Please enter a valid path."
            )
    
    print_step("Directory Configuration", 4, 6)
    ensure_config_directories()
    
    print_step("VPN Setup", 5, 6)
    if get_yes_no_input('🔐 Install and configure PIA VPN?', default=False):
        setup_pia()
    
    print_step("Service Installation", 6, 6)
    install_services_with_selection(media_root, gpu_enabled, ['jellyfin', 'radarr', 'sonarr', 'jellyseerr', 'sabnzbd', 'tdarr_server', 'tdarr_node', 'watchtower', 'portainer'])
    
    print("\n" + "="*80)
    print_success("🎉 MEDIA SERVER SETUP COMPLETE!")
    print("="*80)
    print("Your media server is now ready! Access your services at:")
    local_ip = get_local_ip()
    print(f"  • Jellyfin (Media Server): http://{local_ip}:8096")
    print(f"  • Radarr (Movies): http://{local_ip}:7878")
    print(f"  • Sonarr (TV Shows): http://{local_ip}:8989")
    print(f"  • Jellyseerr (Requests): http://{local_ip}:5055")
    print(f"  • Portainer (Docker Management): https://{local_ip}:9443")
    print("="*80)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print_warning('Setup interrupted by user. Exiting...')
        sys.exit(1)
