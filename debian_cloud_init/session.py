import getpass
import json
import pathlib
import subprocess

from .ui import ask_yes_no, fail, progress

SESSION_FILE = pathlib.Path(".session")


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


def _select_session(sessions: dict) -> tuple[dict, bool]:
    names = list(sessions.keys())

    print("\n--- Sessions ---")
    for i, name in enumerate(names):
        s = sessions[name]
        net = s.get("bridge_interface") or s.get("net_type", "default")
        print(f"  [{i}] {name}  ({s['distro']}, {s['arch']}, {net})")
    print("  [n] Neue VM erstellen")

    choice = input("Auswahl [0]: ").strip().lower()

    if choice == "n":
        return _create_session(sessions)

    try:
        idx = int(choice) if choice else 0
        return sessions[names[idx]], True
    except (ValueError, IndexError):
        print("Ungültige Auswahl, erste Session wird verwendet.")
        return sessions[names[0]], True


def _create_session(sessions: dict) -> tuple[dict, bool]:
    print("\n--- Neue VM-Parameter festlegen ---")

    distros = [
        ("debian", "13"),
        ("debian", "12"),
        ("ubuntu", "24.04"),
        ("ubuntu", "22.04"),
    ]
    print("Betriebssystem wählen:")
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
    hostname = vmname

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

    net_type = "default"
    bridge_interface = None

    if ask_yes_no("Soll das Netzwerk auf 'Bridge' gesetzt werden? (Nein = Default NAT)", default=False):
        result = subprocess.run(["ip", "-o", "link", "show"], capture_output=True, text=True)
        interfaces = []
        for line in result.stdout.splitlines():
            parts = line.split(": ")
            if len(parts) >= 2:
                iface = parts[1].split("@")[0]
                if iface not in ("lo",) and not iface.startswith(("virbr", "docker", "br-", "veth")):
                    interfaces.append(iface)

        if not interfaces:
            print("⚠ Keine physischen Netzwerk-Interfaces gefunden. Verwende NAT.")
        else:
            print("\nVerfügbare Netzwerk-Interfaces:")
            for i, iface in enumerate(interfaces):
                print(f"  [{i}] {iface}")
            sel = input("Interface auswählen [0]: ").strip() or "0"
            try:
                bridge_interface = interfaces[int(sel)]
                net_type = "bridge"
                print(f"✔ Bridge-Interface gewählt: {bridge_interface}")
            except (ValueError, IndexError):
                print("⚠ Ungültige Auswahl. Verwende NAT.")

    session_data = {
        "vmname": vmname,
        "hostname": hostname,
        "username": username,
        "distro": distro,
        "arch": arch,
        "ssh_key": str(ssh_key_path),
        "hashed_password": hashed_password,
        "net_type": net_type,
        "bridge_interface": bridge_interface,
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
