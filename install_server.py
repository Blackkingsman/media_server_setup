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
import platform

# --- Helper Functions ---

def run(cmd, check=True, capture=False):
    print(f"[RUN] {cmd}")
    res = subprocess.run(cmd, shell=True, text=True,
                         stdout=subprocess.PIPE if capture else None,
                         stderr=subprocess.PIPE if capture else None)
    out = res.stdout.strip() if res.stdout else ''
    err = res.stderr.strip() if res.stderr else ''
    if check and res.returncode != 0:
        print(f"[ERROR] Command failed: {cmd}")
        if err:
            print(err)
        sys.exit(res.returncode)
    return out if capture else None

def safe_mkdir(p: Path):
    if not p.exists():
        try:
            p.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            run(f"sudo mkdir -p {p}")
        except Exception:
            pass

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
        print(f"[ERROR] Unsupported platform: {tag}")
        sys.exit(1)
    installers = list(Path(__file__).parent.glob(f"pia-{tag}-*.{ext}"))
    if not installers:
        print(f"[ERROR] No installer for pia-{tag}*.{ext}")
        sys.exit(1)
    return installers[0]

def install_pia():
    if is_installed('piactl'):
        print('[INFO] piactl installed')
        return
    try:
        inst = find_local_installer()
    except SystemExit:
        print("\n[ERROR] No PIA installer found for your system in this directory.")
        print("Please download the appropriate installer from:")
        print("  https://github.com/Blackkingsman/media_server_setup/releases")
        print("and place it in this directory, then rerun the script.")
        sys.exit(1)
    print(f"[STEP] Installing PIA via {inst.name}")
    if not (inst.stat().st_mode & stat.S_IXUSR):
        inst.chmod(inst.stat().st_mode | stat.S_IXUSR)
    run(str(inst))

def login_pia():
    print("[STEP] Checking PIA connection...")
    proc = subprocess.run('piactl connect', shell=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = (proc.stdout or '') + (proc.stderr or '')
    if proc.returncode == 0:
        print(out.strip() or '[INFO] PIA connected')
        return
    if 'requires a logged in account' not in out.lower():
        print(f"[ERROR] Unexpected: {out.strip()}")
        sys.exit(proc.returncode)
    print('[INFO] Not logged in; prompting credentials')
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
        print('[INFO] Docker & Compose present')
        return
    run('sudo apt update')
    run('sudo apt install -y docker.io docker-compose nvidia-container-runtime')
    run('sudo systemctl enable docker --now')
    run(f"sudo usermod -aG docker {os.getlogin()}")

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
        print('[ERROR] No NVIDIA driver')
        sys.exit(1)
    drv = recs[0].split()[0]
    run(f"sudo apt install -y {drv}")
    print('[INFO] Reboot needed')
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

# --- Storage Pool Functions ---

def ensure_media_directories(base):
    bp = Path(base)
    safe_mkdir(bp)
    subs = [
        'Media',
        'Media/radarrconfig',
        'Media/sonarrconfig',
        'Media/Movies',
        'Media/TV Shows',
        'Media/Downloads',
        'Media/jellyseerrconfig',
        'Media/transcode_cache',
        'installscripts/jellyfinconfig',
        'installscripts/jellyfinconfig/cache'
    ]
    for s in subs:
        p = bp / s
        safe_mkdir(p)
        run(f"sudo chown 1000:1000 '{p}'")
    for d in ['/docker/tdarr/server', '/docker/tdarr/configs', '/docker/tdarr/logs']:
        p = Path(d)
        safe_mkdir(p)
        run(f"sudo chown 1000:1000 '{p}'")

def setup_storage_pool(media_root):
    print('[STEP] Configuring media storage pool...')
    BASE_FSTAB = "/etc/fstab.original"
    for m in Path('/mnt').iterdir():
        if m.is_mount():
            run(f'sudo umount {m}', check=False)
        # Only remove the mount point directory itself if it's empty after unmount
        if m.exists() and m.is_dir():
            try:
                m.rmdir()
            except OSError:
                # Directory not empty or other error, skip
                pass
    if input('Reconfigure existing pool? (y/n): ').lower() != 'y':
        print('[INFO] Skip pool')
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
    print('Available block devices:')
    for i, d in enumerate(devs):
        path = f"/dev/{d['name']}"
        uuid = run(f"blkid -s UUID -o value {path}", capture=True)
        print(f"[{i}] {path} (UUID={uuid},fs={d['fstype']},size={d['size']}) {d['model']}")
    idxs = [int(x) for x in input('Enter indices comma-separated: ').split(',')]
    mnt_paths = []
    for i in idxs:
        d = devs[i]
        path = f"/dev/{d['name']}"
        m = Path(f"/mnt/{d['name']}")
        safe_mkdir(m)
        uuid = run(f"blkid -s UUID -o value {path}", capture=True)
        entry = f"UUID={uuid} {m} {d['fstype']} defaults,nofail,uid=1000,gid=1000,windows_names 0 0"
        run(f"echo '{entry}' | sudo tee -a /etc/fstab")
        # If already mounted, ask to unmount and remount
        mounts = run("mount", capture=True)
        if str(m) in mounts or path in mounts:
            resp = input(f"{m} is already mounted. Unmount and remount? (y/n): ").strip().lower()
            if resp == 'y':
                run(f"sudo umount {m}", check=False)
                run(f"sudo mount {m}")
            else:
                print(f"[INFO] Skipping mount for {m}.")
        else:
            run(f"sudo mount {m}")
        mnt_paths.append(str(m))
    pool = media_root
    safe_mkdir(Path(pool))
    src = ':'.join(mnt_paths)
    run(f"printf '\n# MergerFS pool config\n{src} {pool} fuse.mergerfs defaults,allow_other,use_ino,category.create=mfs,nonempty 0 0\n' | sudo tee -a /etc/fstab")
    run('sudo systemctl daemon-reload')
    run('sudo mount -a')
    print(f'[INFO] Pool at {pool}')

# --- Service Installer Templates & Logic ---

def get_paths(media_root):
    # Only Movies, TV, Downloads are required; config dirs will be created if missing
    movies_path = Path(media_root) / "Media/Movies"
    tv_path = Path(media_root) / "Media/TV Shows"
    downloads_path = Path(media_root) / "Media/Downloads"
    radarr_config = Path(media_root) / "Media/radarrconfig"
    sonarr_config = Path(media_root) / "Media/sonarrconfig"
    # Ensure config dirs exist
    for p in [radarr_config, sonarr_config]:
        safe_mkdir(p)
    return {
        "movies_path": str(movies_path),
        "tv_path": str(tv_path),
        "downloads_path": str(downloads_path),
        "radarr_config": str(radarr_config),
        "sonarr_config": str(sonarr_config),
        "media_root": str(media_root)
    }

def prompt_service_options(service, paths):
    # Only prompt for what we don't know
    if service in ("tdarr_node", "tdarr_server"):
        ip = input(f"Enter Tdarr server IP [{get_local_ip()}]: ").strip() or get_local_ip()
        port = input("Enter Tdarr server port [8266]: ").strip() or "8266"
        return (ip, port)
    if service == "watchtower":
        frm = input("Watchtower email FROM: ")
        to = input("Watchtower email TO: ")
        srv = input("Watchtower SMTP server: ")
        prt = input("Watchtower SMTP port [587]: ").strip() or "587"
        usr = input("Watchtower SMTP user: ")
        pwd = getpass.getpass("Watchtower SMTP password: ")
        return (frm, to, srv, prt, usr, pwd)
    return ()

def get_templates(paths, gpu_enabled):
    node_name = "TdarrNode"
    server_name = "TdarrServer"
    gpu_flags = "--gpus all --runtime=nvidia --device=/dev/dri:/dev/dri" if gpu_enabled else ""
    return {
        'radarr': lambda: (
            f"sudo docker run -d --name=radarr "
            f"-e PUID=1000 -e PGID=1000 -e TZ=Etc/UTC "
            f"-p 7878:7878 "
            f"-v \"{paths['radarr_config']}\":/config "
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
            f"-v \"{paths['sonarr_config']}\":/config "
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
            f"-v \"{paths['media_root']}/Media/jellyseerrconfig\":/app/config "
            f"--restart unless-stopped fallenbagel/jellyseerr:latest"
        ),
        'jellyfin': lambda: (
            f"sudo docker run -d --name=jellyfin {gpu_flags} -p 8096:8096 "
            f"-v \"{paths['media_root']}/installscripts/jellyfinconfig\":/config "
            f"-v \"{paths['media_root']}/installscripts/jellyfinconfig/cache\":/cache "
            f"--mount type=bind,source=\"{paths['media_root']}/Media\",target=/media "
            f"--restart unless-stopped jellyfin/jellyfin:latest"
        ),
        'sabnzbd': lambda: (
            f"sudo docker run -d --name=sabnzbd "
            f"-e PUID=1000 -e PGID=1000 -e TZ=Etc/UTC -p 8080:8080 "
            f"-v \"{paths['downloads_path']}\":/downloads "
            f"-v \"{paths['tv_path']}\":/tv "
            f"-v \"{paths['movies_path']}\":/movies "
            f"-v \"{paths['media_root']}/Media/sabnzbdconfig\":/config "
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
    print("\n=== Service Installer ===")
    for i, name in enumerate(templates.keys(), 1):
        mark = '[X]' if name in existing else '[ ]'
        print(f" {i}. {mark} {name}")
    print(" a. Install ALL")
    print(" q. Quit")
    choice = input('Select an option: ').strip().lower()
    to_run = []
    if choice == 'a':
        to_run = list(templates.keys())
    elif choice == 'q':
        sys.exit(0)
    else:
        for part in choice.split(','):
            to_run.append(list(templates.keys())[int(part) - 1])

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
        # For Tdarr Node, ask if using external server
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
        usr = frm  # user and from are the same
        pwd = getpass.getpass("Watchtower SMTP password: ")
        watchtower_args = (frm, to, srv, prt, usr, pwd)

    for svc in to_run:
        if svc in existing:
            print(f"[INFO] Reinstalling {svc}…")
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
        print(f"[STEP] Installing {svc}…")
        run(cmd)
    print('[INFO] Service installation complete')

# --- Main Flow ---


def main():
    # --- Linux-only check and system info ---
    if platform.system().lower() != "linux":
        print("\n" + "="*80)
        print(" Media Server Setup")
        print("="*80)
        print("  This script was built and tested for my personal setup:")
        print("    • Linux Mint")
        print("    • Intel CPU")
        print("    • NVIDIA 1070 Ti GPU")
        print("    • mergerfs for pooling 2 hard drives (no RAID, just max storage for media)")
        print("    • PIA (Private Internet Access) VPN is used for all VPN functionality")
        print("    • PIA VPN installers for Linux, macOS, and Windows (x86, x64, ARM) are included in this repo")
        print()
        print("  This script is intended for Linux systems.")
        print("  Many features may not work or may break on other OSes.")
        print()
        print("  If you have a similar setup (Linux, NVIDIA GPU), this script should work for you.")
        print("  The script will attempt to install the latest NVIDIA driver if needed.")
        print("  If a driver is installed, you must reboot and rerun the script.")
        print("  On rerun, the script will detect the driver and skip the GPU installation step if you enable GPU support.")
        print("="*80)
        proceed = input("Do you want to continue anyway? (y/n): ").strip().lower()
        if proceed != 'y':
            print("Exiting.")
            sys.exit(1)
    print('=== Initial Setup ===')
    install_docker()
    gpu_enabled = input('Enable GPU acceleration? (y/n): ').lower() == 'y'
    if gpu_enabled:
        if not check_nvidia_driver():
            install_nvidia_driver()
        else:
            print("[INFO] NVIDIA driver detected, skipping driver installation.")
        install_nvidia_container_toolkit()
        cv = detect_cuda_version() or input('Enter CUDA version: ')
        test_docker_gpu(cv)
    if input('Setup media storage pool? (y/n): ').lower() == 'y':
        media_root = input("Enter media pool mount point [/mnt/pool]: ").strip() or "/mnt/pool"
        setup_storage_pool(media_root)
    else:
        media_root = input('Enter existing media mount point: ')
        ensure_media_directories(media_root)
    if input('Install and configure PIA VPN? (y/n): ').lower() == 'y':
        install_pia()
        login_pia()
    install_services(media_root, gpu_enabled)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('[INTERRUPTED] Exiting')
        sys.exit(1)