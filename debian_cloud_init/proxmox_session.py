import getpass
import json
import pathlib
import subprocess

from .ui import ask_yes_no, fail, progress

SESSION_FILE = pathlib.Path(".proxmox-session")


def _load_all() -> dict:
    if not SESSION_FILE.exists():
        return {}
    try:
        data = json.loads(SESSION_FILE.read_text())
        # Migriere altes Format (einzelne Session ohne vmname-Key)
        if data and "vmname" in data:
            name = data["vmname"]
            data = {name: data}
            SESSION_FILE.write_text(json.dumps(data, indent=4))
        return data
    except (json.JSONDecodeError, KeyError):
        return {}


def _save_all(sessions: dict):
    SESSION_FILE.write_text(json.dumps(sessions, indent=4))


def _sync_sessions(sessions: dict) -> dict:
    """Prüft für jede Session ob die VM auf Proxmox existiert, entfernt verwaiste Einträge."""
    from .proxmox import ssh_run  # lokaler Import um zirkuläre Imports zu vermeiden

    print("\n--- Sessions mit Proxmox abgleichen ---")

    missing = []
    for name, s in sessions.items():
        host = s["proxmox_host"]
        user = s["proxmox_ssh_user"]
        vmid = s["proxmox_vmid"]
        print(f"  Prüfe {name} (ID {vmid}) auf {host}…", end=" ", flush=True)
        result = ssh_run(host, user, f"qm status {vmid} 2>/dev/null", check=False, capture=True)
        if result.returncode == 0 and result.stdout.strip():
            print(f"✔ {result.stdout.strip()}")
        else:
            print("✘ nicht gefunden")
            missing.append(name)

    if not missing:
        print("\nAlle Sessions haben eine entsprechende VM auf Proxmox.")
        return sessions

    print(f"\n{len(missing)} Session(s) ohne VM auf Proxmox:")
    for name in missing:
        s = sessions[name]
        print(f"  - {name} (ID: {s['proxmox_vmid']}, Host: {s['proxmox_host']})")

    if ask_yes_no("Diese Sessions löschen?"):
        for name in missing:
            del sessions[name]
        _save_all(sessions)
        print(f"✔ {len(missing)} Session(s) entfernt.")

    return sessions


def _select_session(sessions: dict) -> tuple[dict, bool]:
    """Zeigt vorhandene Sessions zur Auswahl. Gibt (session, is_persistent) zurück."""
    names = list(sessions.keys())

    print("\n--- Proxmox Sessions ---")
    for i, name in enumerate(names):
        s = sessions[name]
        print(f"  [{i}] {name}  (ID: {s['proxmox_vmid']}, {s['proxmox_host']}, {s['distro']}, {s['arch']})")
    print("  [n] Neue VM erstellen")
    print("  [i] Bestehende VM importieren")
    print("  [s] Sessions mit Proxmox abgleichen")

    choice = input("Auswahl [0]: ").strip().lower()

    if choice == "n":
        return _create_session(sessions)
    if choice == "i":
        return _import_session(sessions)
    if choice == "s":
        sessions = _sync_sessions(sessions)
        if not sessions:
            return _create_session(sessions)
        return _select_session(sessions)

    try:
        idx = int(choice) if choice else 0
        return sessions[names[idx]], True
    except (ValueError, IndexError):
        print("Ungültige Auswahl, erste Session wird verwendet.")
        return sessions[names[0]], True


def _import_session(sessions: dict) -> tuple[dict, bool]:
    """Importiert eine bereits existierende VM auf Proxmox in die Session-Verwaltung."""
    print("\n--- Bestehende Proxmox VM importieren ---")

    ref = next(iter(sessions.values())) if sessions else {}
    def _default(key, fallback):
        return ref.get(key, fallback)

    host_default = _default("proxmox_host", "")
    host_prompt = f"Proxmox Host [{host_default}]: " if host_default else "Proxmox Host (IP oder Hostname): "
    proxmox_host = input(host_prompt).strip() or host_default
    if not proxmox_host:
        fail("Proxmox Host darf nicht leer sein.")

    proxmox_ssh_user = input(f"SSH-User [{_default('proxmox_ssh_user', 'root')}]: ").strip() or _default("proxmox_ssh_user", "root")
    proxmox_node = input(f"Proxmox Node-Name [{_default('proxmox_node', 'pve')}]: ").strip() or _default("proxmox_node", "pve")
    proxmox_storage = input(f"Storage-Pool [{_default('proxmox_storage', 'local-lvm')}]: ").strip() or _default("proxmox_storage", "local-lvm")
    proxmox_snippets_path = input(f"Snippets-Pfad [{_default('proxmox_snippets_path', '/var/lib/vz/snippets')}]: ").strip() or _default("proxmox_snippets_path", "/var/lib/vz/snippets")
    proxmox_bridge = input(f"Netzwerk-Bridge [{_default('proxmox_bridge', 'vmbr0')}]: ").strip() or _default("proxmox_bridge", "vmbr0")

    vmid_input = input("VM-ID der bestehenden VM: ").strip()
    try:
        proxmox_vmid = int(vmid_input)
    except ValueError:
        fail("VM-ID muss eine Zahl sein.")

    vmname = input("VM-Name: ").strip()
    if not vmname:
        fail("VM-Name darf nicht leer sein.")
    if vmname in sessions:
        fail(f"Session '{vmname}' existiert bereits.")

    username = input("Benutzername in der VM [wlanboy]: ").strip() or "wlanboy"

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

    arch = "arm64" if (input("Architektur ([0] amd64 / [1] arm64) [0]: ").strip() or "0") == "1" else "amd64"

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

    # Passwort optional — bei Import oft nicht bekannt
    hashed_password = ""
    if ask_yes_no("Passwort-Hash hinterlegen? (für spätere Neuerstellung)", default=False):
        password = getpass.getpass("Passwort für User: ")
        progress("Erstelle Passwort-Hash...")
        try:
            hashed_password = subprocess.run(
                ["mkpasswd", "-m", "sha-512", password],
                capture_output=True, text=True, check=True
            ).stdout.strip()
        except Exception:
            fail("mkpasswd fehlt. Installiere: sudo apt install whois")

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

    sessions[vmname] = session_data
    _save_all(sessions)
    print(f"✔ VM '{vmname}' (ID: {proxmox_vmid}) importiert.")
    return session_data, True


def _create_session(sessions: dict) -> tuple[dict, bool]:
    print("\n--- Neue Proxmox VM-Parameter festlegen ---")

    # Proxmox-Verbindung aus vorhandener Session als Default übernehmen
    ref = next(iter(sessions.values())) if sessions else {}
    def _default(key, fallback):
        return ref.get(key, fallback)

    host_default = _default("proxmox_host", "")
    host_prompt = f"Proxmox Host [{host_default}]: " if host_default else "Proxmox Host (IP oder Hostname): "
    proxmox_host = input(host_prompt).strip() or host_default
    if not proxmox_host:
        fail("Proxmox Host darf nicht leer sein.")

    proxmox_ssh_user = input(f"SSH-User [{_default('proxmox_ssh_user', 'root')}]: ").strip() or _default("proxmox_ssh_user", "root")
    proxmox_node = input(f"Proxmox Node-Name [{_default('proxmox_node', 'pve')}]: ").strip() or _default("proxmox_node", "pve")

    vmid_input = input("VM-ID (z.B. 100): ").strip()
    try:
        proxmox_vmid = int(vmid_input)
    except ValueError:
        fail("VM-ID muss eine Zahl sein.")

    proxmox_storage = input(f"Storage-Pool [{_default('proxmox_storage', 'local-lvm')}]: ").strip() or _default("proxmox_storage", "local-lvm")
    proxmox_snippets_path = input(f"Snippets-Pfad [{_default('proxmox_snippets_path', '/var/lib/vz/snippets')}]: ").strip() or _default("proxmox_snippets_path", "/var/lib/vz/snippets")
    proxmox_bridge = input(f"Netzwerk-Bridge [{_default('proxmox_bridge', 'vmbr0')}]: ").strip() or _default("proxmox_bridge", "vmbr0")

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

    print("Ziel-Architektur wählen:")
    print("  [0] amd64 (x86_64)")
    print("  [1] arm64 (aarch64)")
    arch = "arm64" if (input("Auswahl [0]: ").strip() or "0") == "1" else "amd64"

    default_vmname = f"{distro_name}{distro_version.replace('.', '')}"
    vmname = input(f"Name der VM [{default_vmname}]: ").strip() or default_vmname

    if vmname in sessions:
        fail(f"Session '{vmname}' existiert bereits. Bitte anderen Namen wählen.")

    username = input("Benutzername [wlanboy]: ").strip() or "wlanboy"

    password = getpass.getpass("Passwort für User: ")
    progress("Erstelle Passwort-Hash...")
    try:
        hashed_password = subprocess.run(
            ["mkpasswd", "-m", "sha-512", password],
            capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        fail("mkpasswd fehlt. Installiere: sudo apt install whois")

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

    sessions[vmname] = session_data
    _save_all(sessions)
    return session_data, False


def get_or_create_session() -> tuple[dict, bool]:
    sessions = _load_all()

    if not sessions:
        return _create_session(sessions)

    return _select_session(sessions)


def delete_session(vmname: str):
    sessions = _load_all()
    if vmname in sessions:
        del sessions[vmname]
        _save_all(sessions)
