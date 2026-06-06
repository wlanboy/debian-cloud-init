import getpass
import json
import pathlib
import subprocess

from .ui import ask_yes_no, fail, progress

SESSION_FILE = pathlib.Path(".proxmox-session")


def load_session():
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text())
        except (json.JSONDecodeError, KeyError):
            return None
    return None


def save_session(data):
    SESSION_FILE.write_text(json.dumps(data, indent=4))


def get_or_create_session():
    session = load_session()

    if session:
        return session, True

    print("\n--- Proxmox VM-Parameter festlegen ---")

    # Proxmox-Verbindung
    proxmox_host = input("Proxmox Host (IP oder Hostname): ").strip()
    if not proxmox_host:
        fail("Proxmox Host darf nicht leer sein.")

    proxmox_ssh_user = input("SSH-User auf Proxmox [root]: ").strip() or "root"
    proxmox_node = input("Proxmox Node-Name [pve]: ").strip() or "pve"

    # VM-ID
    vmid_input = input("VM-ID (z.B. 100): ").strip()
    try:
        proxmox_vmid = int(vmid_input)
    except ValueError:
        fail("VM-ID muss eine Zahl sein.")

    # Storage
    proxmox_storage = input("Storage-Pool [local-lvm]: ").strip() or "local-lvm"

    # Snippets-Pfad
    proxmox_snippets_path = input("Snippets-Pfad auf Proxmox [/var/lib/vz/snippets]: ").strip() or "/var/lib/vz/snippets"

    # Netzwerk-Bridge
    proxmox_bridge = input("Netzwerk-Bridge [vmbr0]: ").strip() or "vmbr0"

    # Distribution
    distros = [
        ("debian", "13"),
        ("debian", "12"),
        ("ubuntu", "24.04"),
        ("ubuntu", "22.04"),
    ]
    print("\nBetriebssystem wählen:")
    for i, (name, version) in enumerate(distros):
        print(f"  [{i}] {name.capitalize()} {version}")
    distro_choice = input("Auswahl [0]: ").strip() or "0"
    try:
        distro_name, distro_version = distros[int(distro_choice)]
    except (ValueError, IndexError):
        distro_name, distro_version = "debian", "13"
    distro = f"{distro_name}/{distro_version}"

    # Architektur
    print("Ziel-Architektur wählen:")
    print("  [0] amd64 (x86_64)")
    print("  [1] arm64 (aarch64)")
    arch_choice = input("Auswahl [0]: ").strip() or "0"
    arch = "arm64" if arch_choice == "1" else "amd64"

    # VM-Name und User
    default_vmname = f"{distro_name}{distro_version.replace('.', '')}"
    vmname = input(f"Name der VM [{default_vmname}]: ").strip() or default_vmname
    username = input("Benutzername [wlanboy]: ").strip() or "wlanboy"

    # Passwort & Hashing
    password = getpass.getpass("Passwort für User: ")
    progress("Erstelle Passwort-Hash...")
    try:
        hashed_password = subprocess.run(
            ["mkpasswd", "-m", "sha-512", password],
            capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        fail("mkpasswd fehlt. Installiere: sudo apt install whois")

    # SSH-Key Auswahl
    ssh_dir = pathlib.Path.home() / ".ssh"
    pub_keys = sorted([f for f in ssh_dir.glob("*.pub") if f.is_file()])

    if not pub_keys:
        fail("Keine .pub Keys in ~/.ssh gefunden!")

    if len(pub_keys) == 1:
        ssh_key_path = pub_keys[0]
        print(f"Einziger Key automatisch gewählt: {ssh_key_path.name}")
    else:
        print("\nVerfügbare SSH-Keys:")
        for i, key in enumerate(pub_keys):
            print(f"  [{i}] {key.name}")
        sel = input("Key auswählen [0]: ").strip() or "0"
        ssh_key_path = pub_keys[int(sel)]

    session_data = {
        "proxmox_host": proxmox_host,
        "proxmox_ssh_user": proxmox_ssh_user,
        "proxmox_node": proxmox_node,
        "proxmox_vmid": proxmox_vmid,
        "proxmox_storage": proxmox_storage,
        "proxmox_snippets_path": proxmox_snippets_path,
        "proxmox_bridge": proxmox_bridge,
        "vmname": vmname,
        "username": username,
        "distro": distro,
        "arch": arch,
        "ssh_key": str(ssh_key_path),
        "hashed_password": hashed_password,
    }

    save_session(session_data)
    return session_data, False
