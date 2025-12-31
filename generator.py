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
    load_session,
    save_session,
    delete_vm,
    get_vm_ip,
    print_ssh_command,
    ask_yes_no,
)


def main():
    templates_dir = pathlib.Path("templates")

    template_file = templates_dir / "cloud-init-template.yml"
    package_config_file = templates_dir / "package-config.txt"
    system_config_file = templates_dir / "system-config.txt"
    tools_file = templates_dir / "amd64-tools.sh"
    output_file = pathlib.Path("cloud-init.yml")

    # -------------------------------------------------------------------------
    # SESSION LADEN ODER NEUE PARAMETER ABFRAGEN
    # -------------------------------------------------------------------------
    session = load_session()

    if session:
        vmname = session["vmname"]
        username = session["username"]
        arch = session.get("arch", "amd64")
        ssh_key_path = pathlib.Path(session["ssh_key"])
        ssh_key_content = ssh_key_path.read_text().strip()
        hashed_password = session["hashed_password"]

        print(f"Session geladen: VM={vmname}, User={username}, Arch={arch}")

        try:
            state = subprocess.run(
                ["virsh", "domstate", vmname],
                capture_output=True, text=True
            ).stdout.strip()
            
            vm_exists = (state != "")
            vm_running = (state == "running")
        except Exception:
            vm_exists = False
            vm_running = False

        if vm_exists:
            print(f"Die VM '{vmname}' existiert bereits (Status: {state}).")
            
            if vm_running:
                if ask_yes_no("Soll die IP-Adresse ermittelt und der SSH-Befehl angezeigt werden?"):
                    ip = get_vm_ip(vmname)
                    if ip:
                        print_ssh_command(username, ip)
                    else:
                        print("IP konnte (noch) nicht ermittelt werden. (Cloud-Init läuft evtl. noch)")
                    
                    if not ask_yes_no("Möchtest du die VM trotzdem löschen und neu erstellen?"):
                        success("Beende Skript, VM bleibt unverändert.")
                        return # Skript hier beenden
            
            # Wenn nicht laufend oder User will neu bauen:
            if ask_yes_no(f"Soll die existierende VM '{vmname}' gelöscht werden, um sie neu zu erstellen?"):
                delete_vm(vmname)
            else:
                fail("Abbruch durch Nutzer.")

    else:
        # Template prüfen
        if not template_file.is_file():
            fail(f"Template fehlt: {template_file}")

        # Architektur-Abfrage
        print("\nZiel-Architektur wählen:")
        print("  [0] amd64 (x86_64)")
        print("  [1] arm64 (aarch64)")
        arch_choice = input("Auswahl [0]: ").strip() or "0"
        arch = "arm64" if arch_choice == "1" else "amd64"

        vmname = input("Name der VM (z. B. debian13): ").strip()
        if not vmname:
            fail("VM-Name darf nicht leer sein.")

        username = input("Benutzername für die VM: ").strip()
        password = getpass.getpass("Passwort (wird gehasht): ")

        progress("Erstelle Passwort-Hash…")
        try:
            hashed_password = subprocess.run(
                ["mkpasswd", "-m", "sha-512", password],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except Exception:
            fail("mkpasswd fehlt. Installiere: sudo apt install whois")

        # SSH-Key auswählen
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
                    ssh_key_path = pub_keys[sel]
                    ssh_key_content = ssh_key_path.read_text().strip()
                    break
            except Exception:
                pass
            print("Ungültige Auswahl.")

        # Session speichern
        save_session(
            {
                "vmname": vmname,
                "arch": arch,
                "username": username,
                "ssh_key": str(ssh_key_path),
                "cloud_init_path": str(output_file),
                "hashed_password": hashed_password,
            }
        )

    # -------------------------------------------------------------------------
    # PROVISIONIERUNG LÄUFT IMMER (Session oder neu)
    # -------------------------------------------------------------------------

    ensure_file_exists(
        tools_file,
        "https://github.com/wlanboy/vagrantkind/raw/refs/heads/main/amd64-tools.sh",
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

    # Cloud-Init Template laden und anpassen
    try:
        cloud_config = yaml.safe_load(template_file.read_text()) or {}
    except Exception as e:
        fail(f"Fehler beim Laden des Templates: {e}")

    cloud_config["users"] = [
        {
            "name": username,
            "passwd": hashed_password,
            "groups": ["sudo"],
            "shell": "/bin/bash",
            "sudo": ["ALL=(ALL) NOPASSWD:ALL"],
            "ssh_authorized_keys": [ssh_key_content],
        }
    ]

    cloud_config["runcmd"] = package_runcmd + [
        LiteralString(tools_content),
        LiteralString(system_config_content),
    ]

    progress("Schreibe cloud-init.yml…")
    try:
        yaml_body = yaml.dump(
            cloud_config,
            sort_keys=False,
            Dumper=yaml.SafeDumper,
        )
        content = "#cloud-config\n" + yaml_body
        output_file.write_text(content)
    except Exception as e:
        fail(f"Fehler beim Schreiben der cloud-init.yml: {e}")

    progress("Validiere YAML…")
    validate_yaml(output_file)

    success("cloud-init.yml erfolgreich erstellt.")

    print("\n=== VM-Setup ===")

    ensure_isos_folder()
    ensure_base_image(arch)
    ensure_overlay_image(vmname,arch)
    create_vm(vmname,username,arch)

    success("Alle Schritte abgeschlossen.")


if __name__ == "__main__":
    main()
