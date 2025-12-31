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
    delete_vm,
    get_vm_ip,
    print_ssh_command,
    ask_yes_no,
)

from session import (
    get_or_create_session,
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
    session, is_persistent = get_or_create_session()

    vmname = session["vmname"]
    username = session["username"]
    arch = session["arch"]
    ssh_key_path = pathlib.Path(session["ssh_key"])
    ssh_key_content = ssh_key_path.read_text().strip()
    hashed_password = session["hashed_password"]


    if is_persistent:
        print(f"Session geladen: {vmname} ({arch})")
        
        # Prüfung ob VM läuft (Logik wie zuvor besprochen)
        try:
            state = subprocess.run(["virsh", "domstate", vmname], capture_output=True, text=True).stdout.strip()
            if state == "running":
                if ask_yes_no(f"VM '{vmname}' läuft. IP anzeigen?"):
                    ip = get_vm_ip(vmname)
                    if ip:
                        print_ssh_command(username, ip)
                        return
            
            if ask_yes_no(f"Soll die VM '{vmname}' gelöscht und neu erstellt werden?"):
                delete_vm(vmname)
            else:
                return
        except:
            pass

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
