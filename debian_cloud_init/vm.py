import os
import pathlib
import shutil
import subprocess
import tempfile
import time

import grp

from .ui import ask_yes_no, fail, progress, run_cmd, success

ISOS_PATH = pathlib.Path(os.environ.get("ISOS_PATH", "/isos"))


# =============================================================================
# /isos Ordner
# =============================================================================

def ensure_isos_folder():
    if ISOS_PATH.exists():
        stat_info = ISOS_PATH.stat()
        current_uid = os.getuid()
        kvm_gid = grp.getgrnam("kvm").gr_gid

        if stat_info.st_uid == current_uid and stat_info.st_gid == kvm_gid:
            success(f"{ISOS_PATH} existiert und hat korrekte Rechte.")
            return

        print(f"⚠ {ISOS_PATH} existiert, aber Rechte stimmen nicht.")
        if ask_yes_no("Rechte korrigieren?"):
            run_cmd(f"sudo chown {os.getlogin()}:kvm {ISOS_PATH}")
            success("Rechte korrigiert.")
        else:
            fail("Abbruch.")
    else:
        print(f"⚠ {ISOS_PATH} existiert nicht.")
        if ask_yes_no(f"Soll {ISOS_PATH} erzeugt werden?"):
            run_cmd(f"sudo mkdir -p {ISOS_PATH}")
            success(f"{ISOS_PATH} wurde angelegt.")
        else:
            fail("Abbruch.")


# =============================================================================
# Images
# =============================================================================

def _os_variant(distro: str) -> str:
    name, version = distro.split("/", 1)
    if name == "ubuntu":
        return f"ubuntu{version}"
    return f"debian{version}"


def _image_info(distro: str, arch: str) -> tuple[str, str]:
    name, version = distro.split("/", 1)
    if name == "ubuntu":
        image_name = f"ubuntu-{version}-server-cloudimg-{arch}.img"
        url = f"https://cloud-images.ubuntu.com/releases/{version}/release/{image_name}"
    else:
        codename = "trixie" if version == "13" else "bookworm"
        image_name = f"debian-{version}-generic-{arch}.qcow2"
        url = f"https://cdimage.debian.org/cdimage/cloud/{codename}/latest/{image_name}"
    return image_name, url


def ensure_base_image(arch="amd64", distro="debian/13"):
    image_name, url = _image_info(distro, arch)
    base_img = ISOS_PATH / image_name

    if base_img.exists():
        success(f"Basis-Image ({arch}) vorhanden.")
        return

    print(f"⚠ Basis-Image für {arch} fehlt.")
    distro_label = distro.replace("/", " ").capitalize()
    if ask_yes_no(f"Soll das {distro_label} {arch} Cloud-Image heruntergeladen werden?"):
        run_cmd(f"wget -O {ISOS_PATH / image_name} {url}")
        success(f"Basis-Image {arch} heruntergeladen.")
    else:
        fail("Abbruch.")


def ensure_overlay_image(vmname, arch, distro="debian/13"):
    overlay = ISOS_PATH / f"{vmname}.qcow2"
    base_image_name, _ = _image_info(distro, arch)
    base_image_path = ISOS_PATH / base_image_name

    if overlay.exists():
        print(f"⚠ Overlay-Image existiert bereits: {overlay}")
        if ask_yes_no("Löschen und neu erstellen?"):
            overlay.unlink()
        else:
            return

    if not base_image_path.exists():
        fail(f"Basis-Image für {arch} nicht gefunden unter {base_image_path}")

    progress(f"Erstelle Overlay-Image ({arch})…")
    run_cmd(
        f"qemu-img create -f qcow2 "
        f"-F qcow2 "
        f"-o backing_file={base_image_path} "
        f"{overlay} 30G"
    )
    success(f"Overlay-Image erstellt: {overlay} (Basis: {arch})")


# =============================================================================
# VM löschen
# =============================================================================

def delete_vm(vmname, skip_confirm=False):
    result = subprocess.run(
        f"virsh list --all | grep -w {vmname}",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        print("✔ Keine bestehende VM gefunden.")
        return

    print(f"⚠ VM '{vmname}' existiert bereits.")
    if not skip_confirm and not ask_yes_no("Soll die bestehende VM gelöscht werden?"):
        fail("Abbruch.")

    progress("Stoppe VM…")
    subprocess.run(f"virsh destroy {vmname}", shell=True)

    progress("Lösche VM…")
    run_cmd(f"virsh undefine {vmname} --remove-all-storage --nvram")

    overlay = ISOS_PATH / f"{vmname}.qcow2"
    if overlay.exists():
        run_cmd(f"rm -f {overlay}")

    seed_iso = ISOS_PATH / f"{vmname}-seed.iso"
    if seed_iso.exists():
        run_cmd(f"rm -f {seed_iso}")

    success(f"VM '{vmname}' wurde vollständig gelöscht.")


# =============================================================================
# Seed-ISO + VM erstellen
# =============================================================================

def create_seed_iso(vmname: str, network_config_file: pathlib.Path | None = None) -> pathlib.Path:
    """Erstellt eine cloud-init Seed-ISO als SCSI-CDROM.

    EFI + IDE CDROM (intern von --cloud-init) ist inkompatibel mit q35+UEFI.
    Lösung: ISO manuell via genisoimage → als SCSI CDROM anhängen.
    """
    seed_iso = ISOS_PATH / f"{vmname}-seed.iso"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)
        shutil.copy(ISOS_PATH / "cloud-init.yml", tmp / "user-data")
        shutil.copy(ISOS_PATH / "meta-data.yml", tmp / "meta-data")

        extra = ""
        if network_config_file:
            shutil.copy(network_config_file, tmp / "network-config")
            extra = f" {tmp / 'network-config'}"

        run_cmd(
            f"genisoimage -output {seed_iso} -volid cidata -joliet -rock "
            f"{tmp / 'user-data'} {tmp / 'meta-data'}{extra}"
        )

    success(f"Seed-ISO erstellt: {seed_iso}")
    return seed_iso


def create_vm(vmname, username, arch, net_type="default", bridge_interface=None, distro="debian/13", network_config_file=None):
    src = pathlib.Path("cloud-init.yml")
    dst = ISOS_PATH / "cloud-init.yml"
    if not src.exists():
        fail("cloud-init.yml wurde nicht gefunden. Erstelle zuerst die Cloud-Init-Datei.")

    progress(f"Kopiere cloud-init.yml nach {ISOS_PATH}…")
    run_cmd(f"cp {src} {dst}")
    success(f"cloud-init.yml wurde nach {ISOS_PATH} kopiert.")

    if net_type == "bridge" and bridge_interface:
        net_config = f"--network type=direct,source={bridge_interface},source_mode=bridge,model=virtio"
        progress(f"Verwende Bridge-Netzwerk ({bridge_interface})...")
    else:
        net_config = "--network network=default,model=virtio"
        progress("Verwende Default-NAT-Netzwerk...")

    if not ask_yes_no("Soll die VM jetzt angelegt werden?"):
        print("VM-Erstellung übersprungen.")
        return

    if arch == "arm64":
        virt_type = "qemu"
        machine = "virt"
        cpu_model = "max"
        arch_binary = "aarch64"
    else:
        virt_type = "kvm"
        machine = "q35"
        cpu_model = "host-passthrough"
        arch_binary = "x86_64"

    if distro.startswith("ubuntu"):
        seed_iso = create_seed_iso(vmname, network_config_file)
        cloud_init_param = f"--disk {seed_iso},device=cdrom,bus=scsi "
    else:
        cloud_init_param = (
            f"--cloud-init user-data={ISOS_PATH / 'cloud-init.yml'},"
            f"meta-data={ISOS_PATH / 'meta-data.yml'} "
        )

    cmd = (
        f"virt-install "
        f"--name {vmname} "
        f"--arch {arch_binary} "
        f"--machine {machine} "
        f"--cpu {cpu_model} "
        "--memory 4096 "
        "--vcpus 2 "
        f"--disk {ISOS_PATH / f'{vmname}.qcow2'},device=disk,bus=virtio "
        f"--os-variant {_os_variant(distro)} "
        f"--virt-type {virt_type} "
        "--graphics none "
        "--console pty,target_type=serial "
        f"{net_config} "
        f"{cloud_init_param}"
        "--boot uefi "
        "--noautoconsole "
        "--import"
    )

    progress("Erstelle VM…")
    run_cmd(cmd)
    success(f"VM '{vmname}' in {arch} mit ({virt_type}-Modus) wurde angelegt und gestartet.")


# =============================================================================
# IP-Ermittlung + SSH
# =============================================================================

def get_vm_ip(vmname):
    progress("Warte darauf, dass die VM startet…")

    for _ in range(120):
        state = subprocess.run(
            f"virsh domstate {vmname}",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()

        if "running" in state.lower():
            break
        time.sleep(1)
    else:
        fail("VM ist nicht gestartet.")

    progress("Ermittle IP-Adresse der VM…")

    for _ in range(60):
        result = subprocess.run(
            f"virsh domifaddr {vmname} --source agent",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0 and "ipv4" in result.stdout.lower():
            for line in result.stdout.splitlines():
                if "ipv4" in line.lower():
                    ip = line.split()[3].split("/")[0]
                    success(f"IP-Adresse gefunden: {ip}")
                    return ip

        result = subprocess.run(
            "virsh net-dhcp-leases default",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if vmname in line or "ipv4" in line.lower():
                    parts = line.split()
                    for p in parts:
                        if p.count(".") == 3 and "/" in p:
                            ip = p.split("/")[0]
                            success(f"IP-Adresse gefunden: {ip}")
                            return ip

        time.sleep(1)

    fail("Konnte die IP-Adresse der VM nicht ermitteln.")


def print_ssh_command(username, ip):
    print("\n=== SSH-Verbindung ===")
    print(f"ssh {username}@{ip}")
    print("======================\n")
