import json
import pathlib
import subprocess
import tempfile
import time
from typing import Literal, overload

from .ui import ask_int, ask_yes_no, fail, progress, success


# =============================================================================
# SSH / SCP Hilfsfunktionen
# =============================================================================

_SSH_OPTS = ["-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes"]


@overload
def ssh_run(host: str, user: str, cmd: str, *, check: bool = ..., capture: Literal[True]) -> subprocess.CompletedProcess[str]: ...
@overload
def ssh_run(host: str, user: str, cmd: str, *, check: bool = ..., capture: Literal[False] = ...) -> subprocess.CompletedProcess[bytes]: ...
def ssh_run(host: str, user: str, cmd: str, *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    full_cmd = ["ssh"] + _SSH_OPTS + [f"{user}@{host}", cmd]
    if capture:
        result = subprocess.run(full_cmd, capture_output=True, text=True)
        if check and result.returncode != 0:
            fail(f"SSH-Fehler ({host}): {result.stderr.strip() or result.stdout.strip()}")
        return result
    else:
        result = subprocess.run(full_cmd)
        if check and result.returncode != 0:
            fail(f"SSH-Fehler ({host}): Befehl fehlgeschlagen.")
        return result


def scp_to(host: str, user: str, local_path: pathlib.Path, remote_path: str):
    cmd = ["scp"] + _SSH_OPTS + [str(local_path), f"{user}@{host}:{remote_path}"]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        fail(f"SCP fehlgeschlagen: {local_path.name} → {remote_path}")


# =============================================================================
# Cloud-Image auf Proxmox-Host sicherstellen
# =============================================================================

_IMAGE_REMOTE_DIR = "/var/lib/vz/template/iso"


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


def ensure_base_image(host: str, user: str, arch: str, distro: str) -> str:
    """Stellt sicher, dass das Cloud-Image auf dem Proxmox-Host existiert.
    Gibt den Remote-Pfad zurück."""
    image_name, url = _image_info(distro, arch)
    remote_path = f"{_IMAGE_REMOTE_DIR}/{image_name}"

    result = ssh_run(host, user, f"test -f {remote_path}", check=False, capture=True)
    if result.returncode == 0:
        success(f"Basis-Image auf Proxmox vorhanden: {image_name}")
        return remote_path

    print(f"⚠ Basis-Image fehlt auf Proxmox: {image_name}")
    distro_label = distro.replace("/", " ").capitalize()
    if ask_yes_no(f"Soll das {distro_label} {arch} Cloud-Image direkt auf Proxmox heruntergeladen werden?"):
        progress(f"Lade {image_name} auf Proxmox herunter…")
        ssh_run(host, user, f"wget -q --show-progress -O {remote_path} {url}")
        success(f"Basis-Image heruntergeladen: {image_name}")
        return remote_path
    else:
        fail("Abbruch.")


# =============================================================================
# Cloud-Init Snippets hochladen
# =============================================================================

def upload_snippets(host: str, user: str, snippets_path: str, vmname: str,
                    cloud_init_yml: pathlib.Path) -> None:
    """Lädt user-data, meta-data und network-config als Snippets auf Proxmox hoch."""
    meta_content = (
        f"instance-id: {vmname}-{int(time.time())}\n"
        f"local-hostname: {vmname}\n"
    )
    # Wildcard-Match deckt alle Interface-Namen ab (ens18, eth0, enp1s0, …)
    network_content = (
        "version: 2\n"
        "ethernets:\n"
        "  all-en:\n"
        "    match:\n"
        "      name: 'en*'\n"
        "    dhcp4: true\n"
        "    dhcp6: false\n"
        "  all-eth:\n"
        "    match:\n"
        "      name: 'eth*'\n"
        "    dhcp4: true\n"
        "    dhcp6: false\n"
    )

    tmp_files: list[pathlib.Path] = []
    try:
        progress("Lade cloud-init Snippets auf Proxmox hoch…")
        ssh_run(host, user, f"mkdir -p {snippets_path}")

        scp_to(host, user, cloud_init_yml, f"{snippets_path}/{vmname}-user-data.yml")

        for name, content in [
            (f"{vmname}-meta-data.yml", meta_content),
            (f"{vmname}-network-config.yml", network_content),
        ]:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
                f.write(content)
                tmp = pathlib.Path(f.name)
            tmp_files.append(tmp)
            scp_to(host, user, tmp, f"{snippets_path}/{name}")
    finally:
        for tmp in tmp_files:
            tmp.unlink(missing_ok=True)

    success("Snippets hochgeladen: user-data, meta-data, network-config")


# =============================================================================
# VM löschen
# =============================================================================

def delete_vm(host: str, user: str, vmid: int, vmname: str, skip_confirm: bool = False):
    result = ssh_run(host, user, f"qm status {vmid} 2>/dev/null", check=False, capture=True)
    if result.returncode != 0:
        print(f"✔ VM {vmid} existiert nicht.")
        return

    print(f"⚠ VM {vmid} ({vmname}) existiert bereits.")
    if not skip_confirm and not ask_yes_no("Soll die bestehende VM gelöscht werden?"):
        fail("Abbruch.")

    progress(f"Stoppe VM {vmid}…")
    ssh_run(host, user, f"qm stop {vmid} --timeout 30 2>/dev/null || true", check=False)

    progress(f"Lösche VM {vmid}…")
    ssh_run(host, user, f"qm destroy {vmid} --destroy-unreferenced-disks 1 --purge 1")
    success(f"VM {vmid} ({vmname}) wurde gelöscht.")


# =============================================================================
# VM erstellen
# =============================================================================

def create_vm(host: str, user: str, node: str, vmid: int, vmname: str,
              arch: str, distro: str, storage: str, bridge: str,
              snippets_path: str, cloud_init_yml: pathlib.Path):

    upload_snippets(host, user, snippets_path, vmname, cloud_init_yml)
    base_image_path = ensure_base_image(host, user, arch, distro)

    if not ask_yes_no("Soll die VM jetzt angelegt werden?"):
        print("VM-Erstellung übersprungen.")
        return

    DEFAULT_CORES = 2
    DEFAULT_MEMORY = 4096
    DEFAULT_DISK_GB = 30

    if ask_yes_no(
        f"Standard-Größe verwenden? (CPU: {DEFAULT_CORES} Kerne, RAM: {DEFAULT_MEMORY} MB, Disk: {DEFAULT_DISK_GB} GB)",
        default=True,
    ):
        cores = DEFAULT_CORES
        memory = DEFAULT_MEMORY
        disk_gb = DEFAULT_DISK_GB
    else:
        cores = ask_int("CPU-Kerne", DEFAULT_CORES)
        memory = ask_int("RAM in MB", DEFAULT_MEMORY)
        disk_gb = ask_int("Disk-Größe in GB", DEFAULT_DISK_GB)

    # Basis-VM anlegen
    progress(f"Erstelle VM {vmid} ({vmname})…")
    machine = "virt" if arch == "arm64" else "q35"
    ssh_run(host, user,
        f"qm create {vmid}"
        f" --name {vmname}"
        f" --memory {memory}"
        f" --cores {cores}"
        f" --cpu host"
        f" --machine {machine}"
        f" --net0 virtio,bridge={bridge}"
        f" --serial0 socket"
        f" --vga serial0"
        f" --agent enabled=1"
    )

    # Cloud-Image als Disk importieren (zeigt Fortschritt direkt)
    progress("Importiere Cloud-Image als Disk…")
    ssh_run(host, user,
        f"qm importdisk {vmid} {base_image_path} {storage} --format qcow2"
    )

    # Importierte Disk aus qm config lesen (unused0)
    cfg = ssh_run(host, user, f"qm config {vmid}", capture=True)
    disk_ref = None
    for line in cfg.stdout.splitlines():
        if line.startswith("unused0:"):
            disk_ref = line.split(":", 1)[1].strip()

    if not disk_ref:
        fail("Konnte importierte Disk nicht in 'qm config' finden.")

    # Disk als scsi0 anhängen und auf 30G vergrößern
    progress("Konfiguriere Disk…")
    ssh_run(host, user,
        f"qm set {vmid} --scsihw virtio-scsi-pci --scsi0 {disk_ref}"
    )
    ssh_run(host, user, f"qm resize {vmid} scsi0 {disk_gb}G")

    # Cloud-Init Drive hinzufügen
    progress("Füge Cloud-Init Drive hinzu…")
    ssh_run(host, user, f"qm set {vmid} --ide2 {storage}:cloudinit")

    # Snippets als cicustom setzen (user, meta, network explizit — kein --ipconfig0 nötig)
    ssh_run(host, user,
        f'qm set {vmid} --cicustom '
        f'"user=local:snippets/{vmname}-user-data.yml,'
        f'meta=local:snippets/{vmname}-meta-data.yml,'
        f'network=local:snippets/{vmname}-network-config.yml"'
    )

    # Boot-Reihenfolge
    ssh_run(host, user, f"qm set {vmid} --boot order=scsi0")

    # VM starten
    progress(f"Starte VM {vmid}…")
    ssh_run(host, user, f"qm start {vmid}")
    success(f"VM '{vmname}' (ID: {vmid}) wurde angelegt und gestartet.")


# =============================================================================
# IP-Adresse ermitteln (via qemu-guest-agent, Fallback ARP)
# =============================================================================

def _extract_ip_from_interfaces(data) -> str | None:
    """Parst pvesh network-get-interfaces unabhängig vom Wrapper-Format.

    pvesh gibt je nach Proxmox-Version zurück:
      {"result": [...]}   – QAPI-Wrapper
      [...]               – direktes Array
    """
    if isinstance(data, dict):
        interfaces = data.get("result") or data.get("data") or []
    elif isinstance(data, list):
        interfaces = data
    else:
        return None

    for iface in interfaces:
        if not isinstance(iface, dict) or iface.get("name") == "lo":
            continue
        for addr in iface.get("ip-addresses", []):
            if addr.get("ip-address-type") == "ipv4":
                ip = addr.get("ip-address", "")
                if ip and not ip.startswith("127."):
                    return ip
    return None


def get_vm_ip(host: str, user: str, node: str, vmid: int) -> str | None:
    progress("Warte auf VM-Start…")

    for _ in range(60):
        result = ssh_run(host, user, f"qm status {vmid}", capture=True, check=False)
        if "running" in result.stdout:
            break
        time.sleep(2)
    else:
        fail("VM ist nicht gestartet.")

    progress("Ermittle IP via Guest-Agent…")
    print("  (benötigt qemu-guest-agent in der VM)")

    for attempt in range(24):  # 24 × 5 s = 2 Minuten
        result = ssh_run(
            host, user,
            f"pvesh get /nodes/{node}/qemu/{vmid}/agent/network-get-interfaces"
            f" --output-format json 2>/dev/null",
            capture=True, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            try:
                ip = _extract_ip_from_interfaces(json.loads(result.stdout))
                if ip:
                    success(f"IP-Adresse: {ip}")
                    return ip
            except json.JSONDecodeError:
                pass

        print(f"  Versuch {attempt + 1}/24…", end="\r", flush=True)
        time.sleep(5)

    print()
    print("⚠ Guest-Agent hat nicht geantwortet.")
    print("  Mögliche Ursachen:")
    print("  - qemu-guest-agent nicht installiert → in templates/package-config.txt eintragen: qemu-guest-agent")
    print("  - cloud-init läuft noch (kurz warten und erneut versuchen)")
    print("  - VM hat keinen Netzwerkzugang")

    # Fallback: ARP-Tabelle auf dem Proxmox-Host
    progress("Fallback: ARP-Tabelle auf Proxmox prüfen…")
    result = ssh_run(host, user, "arp -n 2>/dev/null", capture=True, check=False)
    if result.returncode == 0:
        entries = [
            line for line in result.stdout.splitlines()
            if line.strip() and "incomplete" not in line and not line.startswith("Address")
        ]
        if entries:
            print("  Bekannte Hosts im ARP-Cache (mögliche VM-IP):")
            for entry in entries:
                print(f"    {entry}")

    return None


def print_ssh_command(username: str, ip: str):
    print("\n=== SSH-Verbindung ===")
    print(f"ssh {username}@{ip}")
    print("======================\n")
