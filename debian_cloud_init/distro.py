import dataclasses


@dataclasses.dataclass(frozen=True)
class Distro:
    """Distro/Version-Paar, z.B. 'debian/13' oder 'ubuntu/24.04'.

    Bündelt die Distro-Logik (os-variant, Image-Name/-URL), die vorher als
    String-Split + if/else in mehreren Modulen dupliziert war.
    """

    name: str
    version: str

    @classmethod
    def parse(cls, value: str) -> Distro:
        name, version = value.split("/", 1)
        return cls(name, version)

    @property
    def is_ubuntu(self) -> bool:
        return self.name == "ubuntu"

    @property
    def os_variant(self) -> str:
        return f"{self.name}{self.version}"

    def image_info(self, arch: str) -> tuple[str, str]:
        """Gibt (Dateiname, Download-URL) des Cloud-Images für die gegebene Architektur zurück."""
        if self.is_ubuntu:
            image_name = f"ubuntu-{self.version}-server-cloudimg-{arch}.img"
            url = f"https://cloud-images.ubuntu.com/releases/{self.version}/release/{image_name}"
        else:
            codename = "trixie" if self.version == "13" else "bookworm"
            image_name = f"debian-{self.version}-generic-{arch}.qcow2"
            url = f"https://cdimage.debian.org/cdimage/cloud/{codename}/latest/{image_name}"
        return image_name, url
