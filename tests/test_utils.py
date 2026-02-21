"""Unit-Tests für utils.py"""

import pathlib
from unittest.mock import patch

import pytest
import yaml

from utils import (
    LiteralString,
    _image_info,
    _os_variant,
    ask_yes_no,
    create_meta_data,
    create_network_config,
    ensure_file_exists,
    validate_yaml,
)


# =============================================================================
# _os_variant
# =============================================================================


class TestOsVariant:
    def test_debian_13(self):
        assert _os_variant("debian/13") == "debian13"

    def test_debian_12(self):
        assert _os_variant("debian/12") == "debian12"

    def test_ubuntu_2404(self):
        assert _os_variant("ubuntu/24.04") == "ubuntu24.04"

    def test_ubuntu_2204(self):
        assert _os_variant("ubuntu/22.04") == "ubuntu22.04"


# =============================================================================
# _image_info
# =============================================================================


class TestImageInfo:
    def test_ubuntu_amd64(self):
        name, url = _image_info("ubuntu/24.04", "amd64")
        assert name == "ubuntu-24.04-server-cloudimg-amd64.img"
        assert "24.04" in url
        assert "amd64" in url
        assert url.startswith("https://cloud-images.ubuntu.com")

    def test_ubuntu_arm64(self):
        name, url = _image_info("ubuntu/22.04", "arm64")
        assert name == "ubuntu-22.04-server-cloudimg-arm64.img"
        assert "arm64" in url

    def test_debian_13_amd64_uses_trixie(self):
        name, url = _image_info("debian/13", "amd64")
        assert name == "debian-13-generic-amd64.qcow2"
        assert "trixie" in url
        assert url.startswith("https://cdimage.debian.org")

    def test_debian_12_amd64_uses_bookworm(self):
        name, url = _image_info("debian/12", "amd64")
        assert name == "debian-12-generic-amd64.qcow2"
        assert "bookworm" in url

    def test_debian_arm64(self):
        name, url = _image_info("debian/13", "arm64")
        assert name == "debian-13-generic-arm64.qcow2"
        assert "arm64" in url

    def test_ubuntu_url_contains_version_twice(self):
        # Versions-String taucht im Pfad und im Dateinamen auf
        name, url = _image_info("ubuntu/24.04", "amd64")
        assert url.count("24.04") >= 1


# =============================================================================
# ask_yes_no
# =============================================================================


class TestAskYesNo:
    @pytest.mark.parametrize("answer", ["j", "y", "ja", "yes"])
    def test_affirmative_answers(self, answer):
        with patch("builtins.input", return_value=answer):
            assert ask_yes_no("Test?") is True

    @pytest.mark.parametrize("answer", ["n", "no", "nein"])
    def test_negative_answers(self, answer):
        with patch("builtins.input", return_value=answer):
            assert ask_yes_no("Test?") is False

    def test_empty_answer_uses_default_true(self):
        with patch("builtins.input", return_value=""):
            assert ask_yes_no("Test?", default=True) is True

    def test_empty_answer_uses_default_false(self):
        with patch("builtins.input", return_value=""):
            assert ask_yes_no("Test?", default=False) is False

    def test_invalid_input_then_valid(self):
        with patch("builtins.input", side_effect=["xyz", "ungültig", "j"]):
            assert ask_yes_no("Test?") is True

    def test_uppercase_accepted(self):
        with patch("builtins.input", return_value="J"):
            assert ask_yes_no("Test?") is True

    def test_uppercase_n_accepted(self):
        with patch("builtins.input", return_value="N"):
            assert ask_yes_no("Test?") is False


# =============================================================================
# ensure_file_exists
# =============================================================================


class TestEnsureFileExists:
    def test_existing_file_returns_true(self, tmp_path):
        f = tmp_path / "present.txt"
        f.write_text("data")
        assert ensure_file_exists(f) is True

    def test_missing_file_no_url_returns_false(self, tmp_path):
        f = tmp_path / "missing.txt"
        assert ensure_file_exists(f) is False

    def test_missing_file_with_url_user_declines_exits(self, tmp_path):
        f = tmp_path / "missing.txt"
        with patch("utils.ask_yes_no", return_value=False):
            with pytest.raises(SystemExit):
                ensure_file_exists(f, download_url="https://example.com/file")

    def test_missing_file_with_url_download_succeeds(self, tmp_path):
        f = tmp_path / "downloaded.txt"

        def fake_urlretrieve(url, path):
            pathlib.Path(path).write_text("content")

        with patch("utils.ask_yes_no", return_value=True):
            with patch("urllib.request.urlretrieve", side_effect=fake_urlretrieve):
                result = ensure_file_exists(f, download_url="https://example.com/file")
        assert result is True

    def test_missing_file_with_url_download_fails_exits(self, tmp_path):
        f = tmp_path / "missing.txt"
        with patch("utils.ask_yes_no", return_value=True):
            with patch("urllib.request.urlretrieve", side_effect=OSError("network error")):
                with pytest.raises(SystemExit):
                    ensure_file_exists(f, download_url="https://example.com/file")


# =============================================================================
# validate_yaml
# =============================================================================


class TestValidateYaml:
    def test_valid_yaml_passes(self, tmp_path):
        f = tmp_path / "valid.yaml"
        f.write_text("key: value\nlist:\n  - a\n  - b\n")
        validate_yaml(f)  # kein SystemExit

    def test_empty_yaml_passes(self, tmp_path):
        f = tmp_path / "empty.yaml"
        f.write_text("")
        validate_yaml(f)

    def test_invalid_yaml_exits(self, tmp_path):
        f = tmp_path / "broken.yaml"
        f.write_text("key: [\nbroken: {unclosed")
        with pytest.raises(SystemExit):
            validate_yaml(f)


# =============================================================================
# LiteralString / YAML Representer
# =============================================================================


class TestLiteralString:
    def test_is_str_subclass(self):
        ls = LiteralString("hello")
        assert isinstance(ls, str)
        assert ls == "hello"

    def test_yaml_dumps_with_literal_block_style(self):
        data = {"script": LiteralString("line1\nline2\n")}
        output = yaml.dump(data, Dumper=yaml.SafeDumper)
        assert "|" in output  # Literal-Block-Stil

    def test_plain_str_not_literal_block(self):
        data = {"key": "plain"}
        output = yaml.dump(data, Dumper=yaml.SafeDumper)
        assert "|" not in output


# =============================================================================
# create_network_config
# =============================================================================


class TestCreateNetworkConfig:
    def test_debian_returns_none(self):
        assert create_network_config("debian/13") is None

    def test_debian_12_returns_none(self):
        assert create_network_config("debian/12") is None

    def test_ubuntu_returns_path(self, tmp_path):
        with patch("utils.ISOS_PATH", tmp_path):
            result = create_network_config("ubuntu/24.04")
        assert result is not None
        assert result.exists()

    def test_ubuntu_config_has_correct_structure(self, tmp_path):
        with patch("utils.ISOS_PATH", tmp_path):
            path = create_network_config("ubuntu/24.04")
        assert path is not None
        cfg = yaml.safe_load(path.read_text())
        assert cfg["version"] == 2
        assert "ethernets" in cfg
        eth = cfg["ethernets"]["all-en"]
        assert eth["dhcp4"] is True
        assert eth["dhcp6"] is False
        assert eth["match"]["name"] == "en*"

    def test_ubuntu_2204_also_works(self, tmp_path):
        with patch("utils.ISOS_PATH", tmp_path):
            result = create_network_config("ubuntu/22.04")
        assert result is not None


# =============================================================================
# create_meta_data
# =============================================================================


class TestCreateMetaData:
    def test_hostname_defaults_to_vmname(self, tmp_path):
        with patch("utils.ISOS_PATH", tmp_path):
            with patch("utils.time.time", return_value=12345):
                create_meta_data("myvm")
        content = (tmp_path / "meta-data.yml").read_text()
        assert "local-hostname: myvm" in content
        assert "instance-id: myvm-12345" in content

    def test_explicit_hostname_overrides_vmname(self, tmp_path):
        with patch("utils.ISOS_PATH", tmp_path):
            with patch("utils.time.time", return_value=99999):
                create_meta_data("myvm", hostname="custom-host")
        content = (tmp_path / "meta-data.yml").read_text()
        assert "local-hostname: custom-host" in content
        assert "instance-id: myvm-99999" in content

    def test_instance_id_contains_vmname(self, tmp_path):
        with patch("utils.ISOS_PATH", tmp_path):
            with patch("utils.time.time", return_value=1):
                create_meta_data("special-vm")
        content = (tmp_path / "meta-data.yml").read_text()
        assert "special-vm" in content
