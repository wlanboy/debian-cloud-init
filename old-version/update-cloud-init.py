#!/usr/bin/env python3

import yaml
import subprocess
import getpass
import pathlib
import sys

def main():
    # 1. Get the path to the cloud-init.yml file with a default value
    default_path = "cloud-init.yml"
    cloud_init_path = input(f"Bitte geben Sie den Pfad zur cloud-init.yml-Datei an (Standard: '{default_path}'): ")
    
    if not cloud_init_path:
        cloud_init_path = default_path
        
    cloud_init_file = pathlib.Path(cloud_init_path)

    if not cloud_init_file.is_file():
        print(f"Fehler: Die Datei '{cloud_init_path}' wurde nicht gefunden.")
        sys.exit(1)

    # 2. Ask for a username
    username = input("Bitte geben Sie den Benutzernamen ein, der in der VM erstellt werden soll: ")
    
    # 3. Ask for a password (hidden input)
    password = getpass.getpass("Bitte geben Sie das Passwort für den Benutzer ein (Eingabe wird verborgen): ")

    # 4. Create the password hash using mkpasswd
    try:
        # Use subprocess to run the mkpasswd command
        print("Erstelle Passwort-Hash...")
        hashed_password = subprocess.run(
            ['mkpasswd', '-m', 'sha-512', password],
            capture_output=True,
            text=True,
            check=True
        ).stdout.strip()
    except FileNotFoundError:
        print("Fehler: Der 'mkpasswd'-Befehl wurde nicht gefunden. Bitte stellen Sie sicher, dass er installiert ist.")
        print("Unter Debian/Ubuntu-Systemen ist er im 'whois'-Paket enthalten.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Fehler beim Erstellen des Passwort-Hash: {e}")
        sys.exit(1)

    # 5. List available SSH public keys
    ssh_dir = pathlib.Path.home() / '.ssh'
    if not ssh_dir.is_dir():
        print(f"Fehler: Das SSH-Verzeichnis '{ssh_dir}' wurde nicht gefunden.")
        sys.exit(1)

    pub_keys = sorted([f for f in ssh_dir.glob('*.pub') if f.is_file()])
    if not pub_keys:
        print("Fehler: Es wurden keine öffentlichen SSH-Schlüssel (*.pub) im Verzeichnis ~/.ssh/ gefunden.")
        sys.exit(1)

    print("\nVerfügbare öffentliche SSH-Schlüssel:")
    for i, key_file in enumerate(pub_keys):
        print(f"  [{i}] {key_file.name}")

    # 6. Let the user select a key
    while True:
        try:
            selection = int(input("Bitte wählen Sie die Nummer des zu verwendenden Schlüssels aus: "))
            if 0 <= selection < len(pub_keys):
                selected_key_file = pub_keys[selection]
                with open(selected_key_file, 'r') as f:
                    ssh_key_content = f.read().strip()
                break
            else:
                print("Ungültige Auswahl. Bitte geben Sie eine gültige Nummer ein.")
        except ValueError:
            print("Ungültige Eingabe. Bitte geben Sie eine Nummer ein.")

    # 7. Read and modify the cloud-init.yml file
    try:
        with open(cloud_init_file, 'r') as f:
            cloud_config = yaml.safe_load(f)
        
        if not cloud_config:
            cloud_config = {}

        # Update the 'users' section
        new_user = {
            'name': username,
            'passwd': hashed_password,
            'groups': ['sudo'],
            'shell': '/bin/bash',
            'sudo': ['ALL=(ALL) NOPASSWD:ALL'],
            'ssh_authorized_keys': [ssh_key_content]
        }
        
        cloud_config['users'] = [new_user]

        # 8. Write the updated YAML data back to the file
        with open(cloud_init_file, 'w') as f:
            yaml.dump(cloud_config, f, sort_keys=False)
        
        print(f"\nErfolg! Die Datei '{cloud_init_path}' wurde aktualisiert.")
        print(f"Der Benutzer '{username}' wurde mit dem neuen Passwort und dem ausgewählten SSH-Schlüssel konfiguriert.")
        
    except Exception as e:
        print(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
