import pathlib
import time
import urllib.request

import yaml

from .ui import ask_yes_no, fail, progress, success

# =============================================================================
# YAML Literal Block Support
# =============================================================================

ISOS_PATH = None  # set via config.py import; accessed as cloud_init.ISOS_PATH


class LiteralString(str):
    pass


def _literal_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.SafeDumper.add_representer(LiteralString, _literal_representer)


# =============================================================================
# Datei-Check + optionaler Download
# =============================================================================

def ensure_file_exists(path: pathlib.Path, download_url: str | None = None) -> bool:
    if path.is_file():
        return True

    print(f"⚠ Datei fehlt: {path}")

    if download_url:
        print("Download möglich über:")
        print(f"  wget {download_url}")
        if ask_yes_no("Jetzt herunterladen?"):
            try:
                progress(f"Lade {path.name} herunter…")
                urllib.request.urlretrieve(download_url, path)
                success("Download abgeschlossen.")
                return True
            except Exception as e:
                fail(f"Download fehlgeschlagen: {e}")
        else:
            fail("Abbruch.")

    return False


# =============================================================================
# YAML Validierung
# =============================================================================

def validate_yaml(path: pathlib.Path):
    try:
        yaml.safe_load(path.read_text())
        success("YAML-Validierung erfolgreich.")
    except yaml.YAMLError as e:
        fail(f"Ungültige YAML-Datei:\n{e}")


# =============================================================================
# Cloud-Init Metadaten
# =============================================================================

def create_meta_data(vmname: str, isos_path: pathlib.Path):
    meta_path = isos_path / "meta-data.yml"
    content = (
        f"instance-id: {vmname}-{int(time.time())}\n"
        f"local-hostname: {vmname}\n"
    )
    try:
        meta_path.write_text(content)
        success(f"meta-data.yml erstellt (Hostname: {vmname}).")
    except Exception as e:
        fail(f"Fehler beim Erstellen der meta-data.yml: {e}")


def create_network_config(distro: str, isos_path: pathlib.Path) -> pathlib.Path | None:
    """Erstellt network-config für Ubuntu (NoCloud-Datasource).

    Wird in der Local-Stage verarbeitet – BEVOR apt-get läuft. Ubuntu-Cloud-Images
    kommen mit einer Netplan-Konfiguration für 'ens3' (i440fx), aber mit q35+virtio
    heißt das Interface 'enp1s0'. Der Wildcard-Match löst das zuverlässig.
    """
    if not distro.startswith("ubuntu"):
        return None

    net_cfg = {
        "version": 2,
        "ethernets": {
            "all-en": {
                "match": {"name": "en*"},
                "dhcp4": True,
                "dhcp6": False,
            }
        },
    }

    path = isos_path / "network-config.yml"
    path.write_text(yaml.dump(net_cfg, sort_keys=False, Dumper=yaml.SafeDumper))
    success(f"network-config.yml für Ubuntu erstellt ({path}).")
    return path
