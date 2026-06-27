#!/usr/bin/env python3

import argparse
import getpass
import pathlib
import shlex
import subprocess
import sys

import yaml

from .cloud_init import (
    LiteralString,
    create_meta_data,
    create_network_config,
    ensure_file_exists,
    validate_yaml,
)
from .session import delete_session, get_or_create_session
from .ui import ask_yes_no, fail, progress, success
from .vm import (
    ISOS_PATH,
    create_vm,
    delete_vm,
    ensure_base_image,
    ensure_isos_folder,
    ensure_overlay_image,
    get_vm_ip,
    print_ssh_command,
)


def _oneline_wizard():
    """Fragt alle VM-Parameter interaktiv ab und gibt den fertigen Einzeiler-Befehl aus."""
    print("=== Oneline-Modus: Parameter sammeln ===")
    print("Am Ende wird der vollständige Befehl ausgegeben.\n")

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

    print("\nZiel-Architektur wählen:")
    print("  [0] amd64 (x86_64)")
    print("  [1] arm64 (aarch64)")
    arch = "arm64" if (input("Auswahl [0]: ").strip() or "0") == "1" else "amd64"

    default_vmname = f"{distro_name}{distro_version.replace('.', '')}"
    vmname = input(f"\nName der VM [{default_vmname}]: ").strip() or default_vmname

    username = input("Benutzername [wlanboy]: ").strip() or "wlanboy"

    password = getpass.getpass("Passwort für User: ")
    print("Erstelle Passwort-Hash...")
    try:
        hashed_password = subprocess.run(
            ["mkpasswd", "-m", "sha-512", password],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except FileNotFoundError:
        print("❌ mkpasswd fehlt. Installiere: sudo apt install whois")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"❌ Fehler beim Hashen des Passworts: {e}")
        sys.exit(1)

    ssh_dir = pathlib.Path.home() / ".ssh"
    pub_keys = sorted([f for f in ssh_dir.glob("*.pub") if f.is_file()])
    if not pub_keys:
        print("❌ Keine .pub Keys in ~/.ssh gefunden!")
        sys.exit(1)
    if len(pub_keys) == 1:
        ssh_key_path = pub_keys[0]
        print(f"Einziger SSH-Key automatisch gewählt: {ssh_key_path.name}")
    else:
        print("\nVerfügbare SSH-Keys:")
        for i, key in enumerate(pub_keys):
            print(f"  [{i}] {key.name}")
        sel = input("Key auswählen [0]: ").strip() or "0"
        try:
            ssh_key_path = pub_keys[int(sel)]
        except (ValueError, IndexError):
            ssh_key_path = pub_keys[0]

    net_type = "default"
    bridge_interface = None

    ans = input("\nBridge-Netzwerk verwenden? (Nein = Default NAT) [j/N]: ").strip().lower()
    if ans in ("j", "y", "ja", "yes"):
        result = subprocess.run(["ip", "-o", "link", "show"], capture_output=True, text=True)
        interfaces = []
        for line in result.stdout.splitlines():
            parts = line.split(": ")
            if len(parts) >= 2:
                iface = parts[1].split("@")[0]
                if iface not in ("lo",) and not iface.startswith(("virbr", "docker", "br-", "veth")):
                    interfaces.append(iface)

        if not interfaces:
            print("⚠ Keine physischen Interfaces gefunden. Verwende NAT.")
        else:
            print("\nVerfügbare Netzwerk-Interfaces:")
            for i, iface in enumerate(interfaces):
                print(f"  [{i}] {iface}")
            sel = input("Interface auswählen [0]: ").strip() or "0"
            try:
                bridge_interface = interfaces[int(sel)]
                net_type = "bridge"
            except (ValueError, IndexError):
                print("⚠ Ungültige Auswahl. Verwende NAT.")

    cmd_parts = [
        "uv", "run", "python", "-m", "debian_cloud_init.generator",
        f"--vmname={vmname}",
        f"--username={username}",
        f"--distro={distro}",
        f"--arch={arch}",
        f"--ssh-key={ssh_key_path}",
        f"--hashed-password={hashed_password}",
        f"--net-type={net_type}",
    ]
    if bridge_interface:
        cmd_parts.append(f"--bridge-interface={bridge_interface}")

    print("\n=== Einzeiler-Befehl ===")
    print(shlex.join(cmd_parts))
    print("=======================\n")


def _session_from_args(args) -> dict:
    return {
        "vmname": args.vmname,
        "hostname": args.vmname,
        "username": args.username,
        "distro": args.distro,
        "arch": args.arch,
        "ssh_key": args.ssh_key,
        "hashed_password": args.hashed_password,
        "net_type": args.net_type,
        "bridge_interface": args.bridge_interface,
    }


def _all_args_provided(args) -> bool:
    required = [args.vmname, args.username, args.distro, args.arch,
                args.ssh_key, args.hashed_password, args.net_type]
    return all(v is not None for v in required)


def main():
    parser = argparse.ArgumentParser(description="Debian/Ubuntu Cloud-Init VM erstellen")
    parser.add_argument("--oneline", action="store_true",
                        help="Interaktiver Wizard, der den fertigen Einzeiler-Befehl ausgibt")
    parser.add_argument("--vmname", help="Name der VM")
    parser.add_argument("--username", help="Benutzername in der VM")
    parser.add_argument("--distro", help="Distro und Version, z.B. debian/13 oder ubuntu/24.04")
    parser.add_argument("--arch", choices=["amd64", "arm64"], help="Ziel-Architektur")
    parser.add_argument("--ssh-key", dest="ssh_key", help="Pfad zum öffentlichen SSH-Key")
    parser.add_argument("--hashed-password", dest="hashed_password",
                        help="Bereits gehashtes Passwort (SHA-512, z.B. via mkpasswd)")
    parser.add_argument("--net-type", dest="net_type", choices=["default", "bridge"],
                        help="Netzwerktyp: default (NAT) oder bridge")
    parser.add_argument("--bridge-interface", dest="bridge_interface",
                        help="Bridge-Interface-Name (nur bei --net-type=bridge)")
    args = parser.parse_args()

    if args.oneline:
        _oneline_wizard()
        return

    templates_dir = pathlib.Path("templates")

    template_file = templates_dir / "cloud-init-template.yml"
    package_config_file = templates_dir / "package-config.txt"
    system_config_file = templates_dir / "system-config.txt"
    tools_file = templates_dir / "amd64-tools.sh"
    output_file = pathlib.Path("cloud-init.yml")

    # -------------------------------------------------------------------------
    # SESSION LADEN ODER NEUE PARAMETER ABFRAGEN
    # -------------------------------------------------------------------------
    if _all_args_provided(args):
        session = _session_from_args(args)
        is_persistent = False
    else:
        session, is_persistent = get_or_create_session()

    vmname = session["vmname"]
    username = session["username"]
    distro = session.get("distro", "debian/13")
    arch = session["arch"]
    ssh_key_path = pathlib.Path(session["ssh_key"])
    ssh_key_content = ssh_key_path.read_text().strip()
    hashed_password = session["hashed_password"]
    net_type = session["net_type"]
    bridge_interface = session.get("bridge_interface")

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
    create_meta_data(vmname, ISOS_PATH)
    success("cloud-init.yml erfolgreich erstellt.")

    if is_persistent:
        print(f"Session geladen: {vmname} ({distro}, {arch})")
        try:
            state = subprocess.run(["virsh", "domstate", vmname], capture_output=True, text=True).stdout.strip()
            if state == "running":
                if ask_yes_no(f"VM '{vmname}' läuft. IP anzeigen?"):
                    ip = get_vm_ip(vmname)
                    if ip:
                        print_ssh_command(username, ip)
                        return

            if ask_yes_no(f"Soll die VM '{vmname}' gelöscht und neu erstellt werden?"):
                delete_vm(vmname, skip_confirm=True)
                delete_session(vmname)
            else:
                return
        except Exception:
            pass

    print("\n=== VM-Setup ===")

    ensure_isos_folder()
    ensure_base_image(arch, distro)
    ensure_overlay_image(vmname, arch, distro)
    network_config_file = create_network_config(distro, ISOS_PATH)
    create_vm(vmname, username, arch, net_type, bridge_interface, distro, network_config_file)

    success("Alle Schritte abgeschlossen.")


if __name__ == "__main__":
    main()
