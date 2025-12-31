import yaml
import subprocess
import pathlib
import sys
import urllib.request
import os
import shutil
import time
import grp
import json
from yaml.representer import SafeRepresenter


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

def fail(msg):
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

def ensure_file_exists(path: pathlib.Path, download_url: str = None) -> bool:
    if path.is_file():
        return True

    print(f"⚠ Datei fehlt: {path}")

    if download_url:
        print(f"Download möglich über:")
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

def delete_vm(vmname):
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

    if not ask_yes_no("Soll die bestehende VM gelöscht werden?"):
        fail("Abbruch.")

    # VM stoppen
    progress("Stoppe VM…")
    subprocess.run(f"virsh destroy {vmname}", shell=True)

    # VM undefinieren
    progress("Lösche VM…")
    run_cmd(f"virsh undefine {vmname} --remove-all-storage --nvram")

    # Overlay löschen
    overlay = pathlib.Path(f"/isos/{vmname}.qcow2")
    if overlay.exists():
        run_cmd(f"rm -f {overlay}")

    success(f"VM '{vmname}' wurde vollständig gelöscht.")

# =============================================================================
# /isos Ordner + Images
# =============================================================================

def ensure_isos_folder():
    isos = pathlib.Path("/isos")

    if isos.exists():
        stat_info = isos.stat()
        owner = stat_info.st_uid
        group = stat_info.st_gid

        current_uid = os.getuid()
        kvm_gid = grp.getgrnam("kvm").gr_gid

        if owner == current_uid and group == kvm_gid:
            success("/isos existiert und hat korrekte Rechte.")
            return
        else:
            print("⚠ /isos existiert, aber Rechte stimmen nicht.")
            if ask_yes_no("Rechte korrigieren?"):
                run_cmd(f"sudo chown {os.getlogin()}:kvm /isos")
                success("Rechte korrigiert.")
            else:
                fail("Abbruch.")
    else:
        print("⚠ /isos existiert nicht.")
        if ask_yes_no("Soll /isos erzeugt werden?"):
            run_cmd("sudo mkdir /isos")
            run_cmd(f"sudo chown {os.getlogin()}:kvm /isos")
            success("/isos wurde angelegt.")
        else:
            fail("Abbruch.")


def ensure_base_image(arch="amd64"):
    # Dateiname basierend auf Architektur
    image_name = f"debian-13-generic-{arch}.qcow2"
    base_img = pathlib.Path(f"/isos/{image_name}")

    if base_img.exists():
        success(f"Basis-Image ({arch}) vorhanden.")
        return

    print(f"⚠ Basis-Image für {arch} fehlt.")

    if ask_yes_no(f"Soll das Debian {arch} Cloud-Image heruntergeladen werden?"):
        # URL Mapping
        base_url = "https://cdimage.debian.org/cdimage/cloud/trixie/latest/"
        url = f"{base_url}debian-13-generic-{arch}.qcow2"
        
        run_cmd(f"wget -O /isos/{image_name} {url}")
        success(f"Basis-Image {arch} heruntergeladen.")
    else:
        fail("Abbruch.")


def ensure_overlay_image(vmname, arch):
    overlay = pathlib.Path(f"/isos/{vmname}.qcow2")
    base_image_path = f"/isos/debian-13-generic-{arch}.qcow2"

    if overlay.exists():
        print(f"⚠ Overlay-Image existiert bereits: {overlay}")
        if ask_yes_no("Löschen und neu erstellen?"):
            overlay.unlink()
        else:
            return

    if not pathlib.Path(base_image_path).exists():
        fail(f"Basis-Image für {arch} nicht gefunden unter {base_image_path}")

    progress(f"Erstelle Overlay-Image ({arch})…")
    run_cmd(
        f"qemu-img create -f qcow2 "
        f"-F qcow2 "  # explizites Backing-Format für neuere qemu-Versionen
        f"-o backing_file={base_image_path} "
        f"/isos/{vmname}.qcow2 30G"
    )
    success(f"Overlay-Image erstellt: /isos/{vmname}.qcow2 (Basis: {arch})")


# =============================================================================
# VM ERSTELLEN
# =============================================================================

def create_vm(vmname,username,arch):
    # cloud-init.yml nach /isos kopieren
    src = pathlib.Path("cloud-init.yml")
    dst = pathlib.Path("/isos/cloud-init.yml")

    if not src.exists():
        fail("cloud-init.yml wurde nicht gefunden. Erstelle zuerst die Cloud-Init-Datei.")

    progress("Kopiere cloud-init.yml nach /isos…")
    run_cmd(f"cp {src} {dst}")
    run_cmd(f"chown {os.getlogin()}:kvm {dst}")
    success("cloud-init.yml wurde nach /isos kopiert.")

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

    cmd = (
        f"virt-install "
        f"--name {vmname} "
        f"--arch {arch_binary} "
        f"--machine {machine} "
        f"--cpu {cpu_model} "
        "--memory 4096 "
        "--vcpus 2 "
        f"--disk /isos/{vmname}.qcow2,device=disk,bus=virtio "
        "--os-variant debian12 "
        f"--virt-type {virt_type} "
        "--graphics none "
        "--console pty,target_type=serial "
        "--network network=default,model=virtio "
        "--cloud-init user-data=/isos/cloud-init.yml "
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

