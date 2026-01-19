import json
import pathlib
import subprocess
import getpass
from utils import progress, fail, ask_yes_no

SESSION_FILE = pathlib.Path(".session")

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
        # Falls die Session existiert, geben wir sie direkt zurück
        # Die Logik zum Prüfen/Löschen der VM machen wir in der main.py
        return session, True

    # --- ELSE: Neue Session abfragen ---
    print("\n--- Neue VM-Parameter festlegen ---")
    
    # Architektur
    print("Ziel-Architektur wählen:")
    print("  [0] amd64 (x86_64)")
    print("  [1] arm64 (aarch64)")
    arch_choice = input("Auswahl [0]: ").strip() or "0"
    arch = "arm64" if arch_choice == "1" else "amd64"

    # Defaults
    vmname = input("Name der VM [debian13]: ").strip() or "debian13"
    username = input("Benutzername [wlanboy]: ").strip() or "wlanboy"
    hostname = vmname

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

    if ask_yes_no("Soll das Netzwerk auf 'Bridge' (enp3s0) gesetzt werden? (Nein = Default NAT)"):
        net_type = "bridge"
    else:
        net_type = "default"

    session_data = {
        "vmname": vmname,
        "hostname": hostname,
        "username": username,
        "arch": arch,
        "ssh_key": str(ssh_key_path),
        "hashed_password": hashed_password,
        "net_type": net_type
    }

    save_session(session_data)
    return session_data, False