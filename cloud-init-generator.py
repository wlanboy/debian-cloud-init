#!/usr/bin/env python3

import yaml
import subprocess
import getpass
import pathlib

from utils import (
    LiteralString,
    ensure_file_exists,
    validate_yaml,
    ensure_isos_folder,
    ensure_base_image,
    ensure_overlay_image,
    create_vm,
    progress,
    success,
    fail,
)


def main():
    templates_dir = pathlib.Path("templates")

    template_file = templates_dir / "cloud-init-template.yml"
    package_config_file = templates_dir / "package-config.txt"
    system_config_file = templates_dir / "system-config.txt"
    tools_file = templates_dir / "amd64-tools.sh"

    # -------------------------------------------------------------------------
    # Cloud-Init Template prüfen
    # -------------------------------------------------------------------------
    if not template_file.is_file():
        fail(f"Template fehlt: {template_file}")

    output_file = pathlib.Path("cloud-init.yml")

    vmname = input("Name der VM (z. B. debian13): ").strip()
    if not vmname:
        fail("VM-Name darf nicht leer sein.")

    # -------------------------------------------------------------------------
    # User / Passwort / SSH-Key
    # -------------------------------------------------------------------------
    username = input("Benutzername für die VM: ").strip()
    password = getpass.getpass("Passwort (wird gehasht): ")

    progress("Erstelle Passwort-Hash…")
    try:
        hashed_password = subprocess.run(
            ['mkpasswd', '-m', 'sha-512', password],
            capture_output=True,
            text=True,
            check=True
        ).stdout.strip()
    except Exception:
        fail("mkpasswd fehlt. Installiere: sudo apt install whois")

    ssh_dir = pathlib.Path.home() / ".ssh"
    pub_keys = sorted([f for f in ssh_dir.glob("*.pub") if f.is_file()])

    if not pub_keys:
        fail("Keine öffentlichen SSH-Keys (*.pub) im ~/.ssh gefunden.")

    print("\nVerfügbare SSH-Keys:")
    for i, key in enumerate(pub_keys):
        print(f"  [{i}] {key.name}")

    while True:
        try:
            sel = int(input("Key auswählen: "))
            if 0 <= sel < len(pub_keys):
                ssh_key_content = pub_keys[sel].read_text().strip()
                break
        except Exception:
            pass
        print("Ungültige Auswahl.")

    # -------------------------------------------------------------------------
    # Externe Dateien prüfen (Templates)
    # -------------------------------------------------------------------------
    ensure_file_exists(
        tools_file,
        "https://github.com/wlanboy/vagrantkind/raw/refs/heads/main/amd64-tools.sh"
    )
    ensure_file_exists(system_config_file)
    ensure_file_exists(package_config_file)

    tools_content = tools_file.read_text()
    system_config_content = system_config_file.read_text()

    package_runcmd = [
        line.strip()
        for line in package_config_file.read_text().splitlines()
        if line.strip()
    ]

    # -------------------------------------------------------------------------
    # Cloud-Init Template laden und anpassen
    # -------------------------------------------------------------------------
    try:
        cloud_config = yaml.safe_load(template_file.read_text()) or {}
    except Exception as e:
        fail(f"Fehler beim Laden des Templates: {e}")

    cloud_config['users'] = [{
        'name': username,
        'passwd': hashed_password,
        'groups': ['sudo'],
        'shell': '/bin/bash',
        'sudo': ['ALL=(ALL) NOPASSWD:ALL'],
        'ssh_authorized_keys': [ssh_key_content]
    }]

    cloud_config['runcmd'] = (
        package_runcmd
        + [
            LiteralString(tools_content),
            LiteralString(system_config_content)
        ]
    )

    # -------------------------------------------------------------------------
    # cloud-init.yml schreiben + validieren
    # -------------------------------------------------------------------------
    progress("Schreibe cloud-init.yml…")
    try:
        output_file.write_text(
            yaml.dump(cloud_config, sort_keys=False, Dumper=yaml.SafeDumper)
        )
    except Exception as e:
        fail(f"Fehler beim Schreiben der cloud-init.yml: {e}")

    progress("Validiere YAML…")
    validate_yaml(output_file)

    success("cloud-init.yml erfolgreich erstellt.")

    # -------------------------------------------------------------------------
    # /isos + Basis-Image + Overlay + VM
    # -------------------------------------------------------------------------
    print("\n=== VM-Setup ===")

    ensure_isos_folder()
    ensure_base_image()
    ensure_overlay_image(vmname)
    create_vm(vmname)

    success("Alle Schritte abgeschlossen.")


if __name__ == "__main__":
    main()
