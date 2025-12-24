import yaml
import subprocess
import pathlib
import sys
import urllib.request
import os
import time
import grp
import json

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

def ask_yes_no(question):
    answer = input(f"{question} (y/n): ").strip().lower()
    return answer == "y"

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


def ensure_base_image():
    base_img = pathlib.Path("/isos/debian-13-generic-amd64.qcow2")

    if base_img.exists():
        success("Basis-Image vorhanden.")
        return

    print("⚠ Basis-Image fehlt.")

    if ask_yes_no("Soll das Debian Cloud-Image heruntergeladen werden?"):
        url = "https://cdimage.debian.org/cdimage/cloud/trixie/latest/debian-13-generic-amd64.qcow2"
        run_cmd(f"wget -O /isos/debian-13-generic-amd64.qcow2 {url}")
        success("Basis-Image heruntergeladen.")
    else:
        fail("Abbruch.")


def ensure_overlay_image(vmname):
    overlay = pathlib.Path(f"/isos/{vmname}.qcow2")

    if overlay.exists():
        print(f"⚠ Overlay-Image existiert bereits: {overlay}")
        if ask_yes_no("Löschen und neu erstellen?"):
            overlay.unlink()
        else:
            fail("Abbruch.")

    progress("Erstelle Overlay-Image…")
    run_cmd(
        f"qemu-img create -f qcow2 "
        f"-o backing_file=/isos/debian-13-generic-amd64.qcow2,backing_fmt=qcow2 "
        f"/isos/{vmname}.qcow2 30G"
    )
    success(f"Overlay-Image erstellt: /isos/{vmname}.qcow2")


def create_vm(vmname):
    # cloud-init.yml nach /isos kopieren
    src = pathlib.Path("cloud-init.yml")
    dst = pathlib.Path("/isos/cloud-init.yml")

    if not src.exists():
        fail("cloud-init.yml wurde nicht gefunden. Erstelle zuerst die Cloud-Init-Datei.")

    progress("Kopiere cloud-init.yml nach /isos…")
    run_cmd(f"cp {src} {dst}")
    run_cmd(f"chown {os.getlogin()}:kvm {dst}")
    success("cloud-init.yml wurde nach /isos kopiert.")

    # VM anlegen?
    if not ask_yes_no("Soll die VM jetzt angelegt werden?"):
        print("VM-Erstellung übersprungen.")
        return

    cmd = (
        f"virt-install "
        f"--name {vmname} "
        "--memory 4096 "
        "--vcpus 4 "
        f"--disk /isos/{vmname}.qcow2,device=disk,bus=virtio "
        "--os-variant debian12 "
        "--virt-type kvm "
        "--graphics none "
        "--console pty,target_type=serial "
        "--network network=default,model=virtio "
        "--cloud-init user-data=/isos/cloud-init.yml "
        "--boot uefi "
        "--import"
    )

    progress("Erstelle VM…")
    run_cmd(cmd)
    success(f"VM '{vmname}' wurde angelegt.")

def load_session():
    session_file = pathlib.Path(".session")
    if not session_file.exists():
        return None

    print("⚠ Eine bestehende Session wurde gefunden.")
    if ask_yes_no("Soll diese Session wiederholt werden?"):
        try:
            return json.loads(session_file.read_text())
        except Exception:
            fail("Session-Datei ist beschädigt.")
    return None

def save_session(data):
    session_file = pathlib.Path(".session")
    session_file.write_text(json.dumps(data, indent=2))
    success("Session wurde gespeichert.")

def delete_vm(vmname):
    # Prüfen, ob VM existiert
    result = subprocess.run(
        f"virsh list --all | grep -w {vmname}",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if result.returncode != 0:
        print("✔ Keine bestehende VM gefunden.")
        return

    print(f"⚠ VM '{vmname}' existiert bereits.")

    if not ask_yes_no("Soll die bestehende VM gelöscht werden?"):
        fail("Abbruch.")

    progress("Stoppe VM…")
    run_cmd(f"sudo virsh destroy {vmname}")

    progress("Lösche VM…")
    run_cmd(f"sudo virsh undefine {vmname} --remove-all-storage")

    overlay = pathlib.Path(f"/isos/{vmname}.qcow2")
    if overlay.exists():
        run_cmd(f"sudo rm -f {overlay}")

    success(f"VM '{vmname}' wurde vollständig gelöscht.")

