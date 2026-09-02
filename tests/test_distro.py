"""Unit-Tests für distro.py"""

import pytest

from debian_cloud_init.distro import Distro

# =============================================================================
# Distro.parse / os_variant
# =============================================================================


class TestOsVariant:
    def test_debian_13(self):
        assert Distro.parse("debian/13").os_variant == "debian13"

    def test_debian_12(self):
        assert Distro.parse("debian/12").os_variant == "debian12"

    def test_ubuntu_2404(self):
        assert Distro.parse("ubuntu/24.04").os_variant == "ubuntu24.04"

    def test_ubuntu_2204(self):
        assert Distro.parse("ubuntu/22.04").os_variant == "ubuntu22.04"

    def test_missing_slash_raises(self):
        with pytest.raises((ValueError, IndexError)):
            Distro.parse("debian")

    def test_ubuntu_starts_with_ubuntu(self):
        assert Distro.parse("ubuntu/22.04").os_variant.startswith("ubuntu")

    def test_debian_starts_with_debian(self):
        assert Distro.parse("debian/12").os_variant.startswith("debian")


# =============================================================================
# Distro.image_info
# =============================================================================


class TestImageInfo:
    def test_ubuntu_amd64(self):
        name, url = Distro.parse("ubuntu/24.04").image_info("amd64")
        assert name == "ubuntu-24.04-server-cloudimg-amd64.img"
        assert url.startswith("https://cloud-images.ubuntu.com")
        assert "amd64" in url

    def test_ubuntu_arm64(self):
        name, url = Distro.parse("ubuntu/22.04").image_info("arm64")
        assert name == "ubuntu-22.04-server-cloudimg-arm64.img"
        assert "arm64" in url

    def test_debian_13_uses_trixie(self):
        name, url = Distro.parse("debian/13").image_info("amd64")
        assert name == "debian-13-generic-amd64.qcow2"
        assert "trixie" in url
        assert url.startswith("https://cdimage.debian.org")

    def test_debian_12_uses_bookworm(self):
        _, url = Distro.parse("debian/12").image_info("amd64")
        assert "bookworm" in url

    def test_debian_arm64(self):
        name, url = Distro.parse("debian/13").image_info("arm64")
        assert "arm64" in name
        assert "arm64" in url

    def test_missing_slash_raises(self):
        with pytest.raises((ValueError, IndexError)):
            Distro.parse("ubuntu").image_info("amd64")

    def test_unknown_debian_version_falls_back_to_bookworm(self):
        """Dokumentiert den Bug: Debian 14+ wird fälschlich als 'bookworm' aufgelöst."""
        _, url = Distro.parse("debian/14").image_info("amd64")
        assert "bookworm" in url

    def test_ubuntu_url_ends_with_img(self):
        _, url = Distro.parse("ubuntu/24.04").image_info("amd64")
        assert url.endswith(".img")

    def test_debian_url_ends_with_qcow2(self):
        _, url = Distro.parse("debian/13").image_info("amd64")
        assert url.endswith(".qcow2")
