def machine_type(arch: str) -> str:
    """QEMU-Maschinentyp für die Ziel-Architektur (gilt für libvirt und Proxmox/qm gleichermaßen)."""
    return "virt" if arch == "arm64" else "q35"
