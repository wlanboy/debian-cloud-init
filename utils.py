import yaml
import subprocess
import pathlib
import sys
import urllib.request
import os
import shutil
import tempfile
import time
import grp
from typing import NoReturn

# =============================================================================
# KONFIGURATION
# =============================================================================

ISOS_PATH = pathlib.Path(os.environ.get("ISOS_PATH", "/isos"))


# =============================================================================
# YAML Literal Block Support
# =============================================================================

class LiteralString(str):
    pass

def literal_representer(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')

yaml.SafeDumper.add_representer(LiteralString, literal_representer)


# =============================================================================
# Helper Functions
# =============================================================================

def progress(msg):
    print(f"\n➡ {msg}")
    time.sleep(0.3)

def success(msg):
    print(f"✔ {msg}")

def fail(msg) -> NoReturn:
    print(f"❌ {msg}")
    sys.exit(1)

def ask_yes_no(question, default=True):
    suffix = "[J/n]" if default else "[j/N]"
    while True:
        ans = input(f"{question} {suffix}: ").strip().lower()
        
        if not ans:
            return default
        if ans in ["j", "y", "ja", "yes"]:
            return True
        if ans in ["n", "no", "nein"]:
            return False
        
        print("Bitte mit 'j' für Ja oder 'n' für Nein antworten.")

def run_cmd(cmd):
    print(f"→ {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        fail("Fehler beim Ausführen des Befehls.")


# =============================================================================
# Datei-Check + optionaler Download
# =============================================================================

def ensure_file_exists(path: pathlib.Path, download_url: str | None = None) -> bool:
    if path.is_file():
        return True

    print(f"⚠ Datei fehlt: {path}")

    if download_url:
        print("Download möglich über:")
        print(f"  wget {download_url}")

        if ask_yes_no("Jetzt herunterladen?"):
            try:
                progress(f"Lade {path.name} herunter…")
                urllib.request.urlretrieve(download_url, path)
                success("Download abgeschlossen.")
                return True
            except Exception as e:
                fail(f"Download fehlgeschlagen: {e}")
        else:
            fail("Abbruch.")

    return False


# =============================================================================
# YAML VALIDIERUNG
# =============================================================================

def validate_yaml(path: pathlib.Path):
    try:
        yaml.safe_load(path.read_text())
        success("YAML-Validierung erfolgreich.")
    except yaml.YAMLError as e:
        fail(f"Ungültige YAML-Datei:\n{e}")


# =============================================================================
# VM LÖSCHEN
# =============================================================================

def delete_vm(vmname, skip_confirm=False):
    # Prüfen, ob VM existiert
    result = subprocess.run(
        f"virsh list --all | grep -w {vmname}",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        print("✔ Keine bestehende VM gefunden.")
        return

    print(f"⚠ VM '{vmname}' existiert bereits.")

    if not skip_confirm and not ask_yes_no("Soll die bestehende VM gelöscht werden?"):
        fail("Abbruch.")

    # VM stoppen
    progress("Stoppe VM…")
    subprocess.run(f"virsh destroy {vmname}", shell=True)

    # VM undefinieren
    progress("Lösche VM…")
    run_cmd(f"virsh undefine {vmname} --remove-all-storage --nvram")

    # Overlay löschen
    overlay = ISOS_PATH / f"{vmname}.qcow2"
    if overlay.exists():
        run_cmd(f"rm -f {overlay}")

    # Seed-ISO löschen
    seed_iso = ISOS_PATH / f"{vmname}-seed.iso"
    if seed_iso.exists():
        run_cmd(f"rm -f {seed_iso}")

    success(f"VM '{vmname}' wurde vollständig gelöscht.")

# =============================================================================
# /isos Ordner + Images
# =============================================================================

def ensure_isos_folder():
    isos = ISOS_PATH

    if isos.exists():
        stat_info = isos.stat()
        owner = stat_info.st_uid
        group = stat_info.st_gid

        current_uid = os.getuid()
        kvm_gid = grp.getgrnam("kvm").gr_gid

        if owner == current_uid and group == kvm_gid:
            success(f"{ISOS_PATH} existiert und hat korrekte Rechte.")
            return
        else:
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
            #run_cmd(f"sudo chown {os.getlogin()}:kvm {ISOS_PATH}")
            success(f"{ISOS_PATH} wurde angelegt.")
        else:
            fail("Abbruch.")


def _os_variant(distro: str) -> str:
    """Gibt den osinfo/virt-install os-variant String zurück."""
    name, version = distro.split("/", 1)
    if name == "ubuntu":
        return f"ubuntu{version}"
    return f"debian{version}"


def _image_info(distro: str, arch: str) -> tuple[str, str]:
    """Gibt (image_name, download_url) für die angegebene Distro/Arch zurück."""
    name, version = distro.split("/", 1)
    if name == "ubuntu":
        image_name = f"ubuntu-{version}-server-cloudimg-{arch}.img"
        url = f"https://cloud-images.ubuntu.com/releases/{version}/release/{image_name}"
    else:
        # Debian
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
    distro_label = distro.replace("/", " ")

    if ask_yes_no(f"Soll das {distro_label.capitalize()} {arch} Cloud-Image heruntergeladen werden?"):
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
        f"-F qcow2 "  # explizites Backing-Format für neuere qemu-Versionen
        f"-o backing_file={base_image_path} "
        f"{overlay} 30G"
    )
    success(f"Overlay-Image erstellt: {overlay} (Basis: {arch})")

def create_network_config(distro: str) -> pathlib.Path | None:
    """Erstellt eine separate network-config Datei für Ubuntu (NoCloud-Datasource).

    Diese Datei wird von cloud-init in der Local-Stage verarbeitet – also BEVOR
    netzwerk-abhängige Operationen (apt-get) laufen. Das ist der entscheidende
    Unterschied zum 'network'-Key in user-data, der erst in der Config-Stage greift.
    Ubuntu-Cloud-Images kommen mit einer vordefinierten Netplan-Konfiguration für
    'ens3' (i440fx-Naming), aber mit q35+virtio heißt das Interface 'enp1s0'.
    """
    if not distro.startswith("ubuntu"):
        return None

    net_cfg = {
        "version": 2,
        "ethernets": {
            "all-en": {
                "match": {"name": "en*"},
                "dhcp4": True,
                "dhcp6": False,
            }
        },
    }

    path = ISOS_PATH / "network-config.yml"
    content = yaml.dump(net_cfg, sort_keys=False, Dumper=yaml.SafeDumper)
    path.write_text(content)
    #run_cmd(f"chown {os.getlogin()}:kvm {path}")
    success(f"network-config.yml für Ubuntu erstellt ({path}).")
    return path


def create_meta_data(vmname, hostname=None):
    """Erzeugt eine meta-data.yml in /isos für den Hostnamen."""
    if hostname is None:
        hostname = vmname
        
    meta_path = ISOS_PATH / "meta-data.yml"
    
    # Instance-ID ist oft ein Zeitstempel oder der VM-Name
    # Sie signalisiert cloud-init, dass es sich um eine neue Instanz handelt
    content = (
        f"instance-id: {vmname}-{int(time.time())}\n"
        f"local-hostname: {hostname}\n"
    )
    
    try:
        meta_path.write_text(content)
        #run_cmd(f"chown {os.getlogin()}:kvm {meta_path}")
        success(f"meta-data.yml erstellt (Hostname: {hostname}).")
    except Exception as e:
        fail(f"Fehler beim Erstellen der meta-data.yml: {e}")

# =============================================================================
# VM ERSTELLEN
# =============================================================================

def create_seed_iso(vmname: str, network_config_file: pathlib.Path | None = None) -> pathlib.Path:
    """Erstellt eine cloud-init Seed-ISO und bindet sie als SCSI-CDROM ein.

    EFI + IDE CDROM (was --cloud-init intern erzeugt) ist inkompatibel.
    Lösung: ISO manuell via genisoimage bauen → als SCSI CDROM anhängen.
    Die NoCloud-Datasource erwartet die Dateinamen: user-data, meta-data, network-config.
    """
    seed_iso = ISOS_PATH / f"{vmname}-seed.iso"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)
        shutil.copy(ISOS_PATH / "cloud-init.yml", tmp / "user-data")
        shutil.copy(ISOS_PATH / "meta-data.yml",  tmp / "meta-data")

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
    # cloud-init.yml nach ISOS_PATH kopieren
    src = pathlib.Path("cloud-init.yml")
    dst = ISOS_PATH / "cloud-init.yml"
    if not src.exists():
        fail("cloud-init.yml wurde nicht gefunden. Erstelle zuerst die Cloud-Init-Datei.")

    progress(f"Kopiere cloud-init.yml nach {ISOS_PATH}…")
    run_cmd(f"cp {src} {dst}")
    #run_cmd(f"chown {os.getlogin()}:kvm {dst}")
    #run_cmd(f"chown {os.getlogin()}:kvm {dstmd}")
    success(f"cloud-init.yml wurde nach {ISOS_PATH} kopiert.")

    # Netzwerk-Konfiguration wählen
    if net_type == "bridge" and bridge_interface:
        # Direct/Bridge Modus (macvtap)
        net_config = f"--network type=direct,source={bridge_interface},source_mode=bridge,model=virtio"
        progress(f"Verwende Bridge-Netzwerk ({bridge_interface})...")
    else:
        # Standard NAT
        net_config = "--network network=default,model=virtio"
        progress("Verwende Default-NAT-Netzwerk...")

    if not ask_yes_no("Soll die VM jetzt angelegt werden?"):
        print("VM-Erstellung übersprungen.")
        return
    
    if arch == "arm64":
        virt_type = "qemu"        # KVM geht nicht bei arch-cross
        machine = "virt"          # Standard für ARM64
        cpu_model = "max"         # 'max' emuliert alle verfügbaren ARM-Features
        arch_binary = "aarch64"
    else:
        virt_type = "kvm"         # Nativ auf Ryzen 9
        machine = "q35"
        cpu_model = "host-passthrough"
        arch_binary = "x86_64"

    # Ubuntu: EFI + IDE CDROM (intern von --cloud-init) ist inkompatibel.
    # Lösung: Seed-ISO manuell bauen und als SCSI CDROM einbinden.
    # Debian: --cloud-init funktioniert weiterhin.
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

def get_vm_ip(vmname):
    progress("Warte darauf, dass die VM startet…")

    # Warten, bis die VM läuft
    for _ in range(120):
        state = subprocess.run(
            f"virsh domstate {vmname}",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        ).stdout.strip()

        if "running" in state.lower():
            break

        time.sleep(1)
    else:
        fail("VM ist nicht gestartet.")

    progress("Ermittle IP-Adresse der VM…")

    # Bis zu 60 Sekunden auf IP warten
    for _ in range(60):
        # Versuch 1: QEMU-Agent (beste Methode)
        result = subprocess.run(
            f"virsh domifaddr {vmname} --source agent",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode == 0 and "ipv4" in result.stdout.lower():
            for line in result.stdout.splitlines():
                if "ipv4" in line.lower():
                    ip = line.split()[3].split("/")[0]
                    success(f"IP-Adresse gefunden: {ip}")
                    return ip

        # Versuch 2: DHCP-Leases
        result = subprocess.run(
            "virsh net-dhcp-leases default",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
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

