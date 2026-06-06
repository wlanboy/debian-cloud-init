#!/usr/bin/env python3

import pathlib

import yaml

from .cloud_init import (
    LiteralString,
    ensure_file_exists,
    validate_yaml,
)
from .proxmox import (
    create_vm,
    delete_vm,
    get_vm_ip,
    print_ssh_command,
    ssh_run,
)
from .proxmox_session import delete_session, get_or_create_session
from .ui import ask_yes_no, fail, progress, success


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

    host = session["proxmox_host"]
    ssh_user = session["proxmox_ssh_user"]
    node = session["proxmox_node"]
    vmid = session["proxmox_vmid"]
    storage = session["proxmox_storage"]
    snippets_path = session["proxmox_snippets_path"]
    bridge = session["proxmox_bridge"]

    vmname = session["vmname"]
    username = session["username"]
    distro = session.get("distro", "debian/13")
    arch = session["arch"]
    ssh_key_path = pathlib.Path(session["ssh_key"])
    ssh_key_content = ssh_key_path.read_text().strip()
    hashed_password = session["hashed_password"]

    # -------------------------------------------------------------------------
    # CLOUD-INIT GENERIEREN (immer, unabhängig vom VM-Zustand)
    # -------------------------------------------------------------------------

    ensure_file_exists(
        tools_file,
        "https://github.com/wlanboy/vagrantkind/raw/refs/heads/main/amd64-tools.sh",
    )
    if not ensure_file_exists(system_config_file):
        fail(f"Pflichtdatei fehlt: {system_config_file}")
    if not ensure_file_exists(package_config_file):
        fail(f"Pflichtdatei fehlt: {package_config_file}")

    tools_content = tools_file.read_text()
    system_config_content = system_config_file.read_text()
    package_runcmd = [
        line.strip()
        for line in package_config_file.read_text().splitlines()
        if line.strip()
    ]

    try:
        cloud_config = yaml.safe_load(template_file.read_text()) or {}
    except Exception as e:
        fail(f"Fehler beim Laden des Templates: {e}")

    # Proxmox-spezifisch: qemu-guest-agent für IP-Erkennung via pvesh
    packages = cloud_config.get("packages", [])
    cloud_config["packages"] = packages
    cloud_config.setdefault("package_update", True)

    cloud_config["users"] = [
        {
            "name": username,
            "passwd": hashed_password,
            "lock_passwd": False,
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
        yaml_body = yaml.dump(cloud_config, sort_keys=False, Dumper=yaml.SafeDumper)
        output_file.write_text("#cloud-config\n" + yaml_body)
    except Exception as e:
        fail(f"Fehler beim Schreiben der cloud-init.yml: {e}")

    progress("Validiere YAML…")
    validate_yaml(output_file)
    success("cloud-init.yml erfolgreich erstellt.")

    if is_persistent:
        print(f"Session geladen: {vmname} (ID {vmid}) auf {host} ({distro}, {arch})")
        result = ssh_run(host, ssh_user, f"qm status {vmid} 2>/dev/null", check=False, capture=True)
        if "running" in result.stdout:
            if ask_yes_no(f"VM {vmid} läuft. IP anzeigen?"):
                ip = get_vm_ip(host, ssh_user, node, vmid)
                if ip:
                    print_ssh_command(username, ip)
                return

        if ask_yes_no(f"Soll VM {vmid} ({vmname}) gelöscht und neu erstellt werden?"):
            delete_vm(host, ssh_user, vmid, vmname, skip_confirm=True)
            delete_session(vmname)
        else:
            return

    # -------------------------------------------------------------------------
    # VM AUF PROXMOX ANLEGEN
    # -------------------------------------------------------------------------

    print(f"\n=== Proxmox VM-Setup ({host}, Node: {node}) ===")

    create_vm(
        host=host,
        user=ssh_user,
        node=node,
        vmid=vmid,
        vmname=vmname,
        arch=arch,
        distro=distro,
        storage=storage,
        bridge=bridge,
        snippets_path=snippets_path,
        cloud_init_yml=output_file,
    )

    success("Alle Schritte abgeschlossen.")


if __name__ == "__main__":
    main()
