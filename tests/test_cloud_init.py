"""Unit-Tests für cloud_init.py"""

import pathlib
from unittest.mock import patch

import pytest
import yaml

from debian_cloud_init.cloud_init import (
    LiteralString,
    create_meta_data,
    create_network_config,
    ensure_file_exists,
    validate_yaml,
)


# =============================================================================
# LiteralString / YAML Representer
# =============================================================================


class TestLiteralString:
    def test_is_str_subclass(self):
        assert isinstance(LiteralString("hello"), str)

    def test_yaml_dumps_with_literal_block_style(self):
        output = yaml.dump({"script": LiteralString("line1\nline2\n")}, Dumper=yaml.SafeDumper)
        assert "|" in output

    def test_plain_str_not_literal_block(self):
        output = yaml.dump({"key": "plain"}, Dumper=yaml.SafeDumper)
        assert "|" not in output


# =============================================================================
# ensure_file_exists
# =============================================================================


class TestEnsureFileExists:
    def test_existing_file_returns_true(self, tmp_path):
        f = tmp_path / "present.txt"
        f.write_text("data")
        assert ensure_file_exists(f) is True

    def test_missing_file_no_url_returns_false(self, tmp_path):
        assert ensure_file_exists(tmp_path / "missing.txt") is False

    def test_missing_file_with_url_user_declines_exits(self, tmp_path):
        with patch("debian_cloud_init.cloud_init.ask_yes_no", return_value=False):
            with pytest.raises(SystemExit):
                ensure_file_exists(tmp_path / "missing.txt", download_url="https://example.com/file")

    def test_missing_file_with_url_download_succeeds(self, tmp_path):
        f = tmp_path / "downloaded.txt"

        def fake_urlretrieve(url, path):
            pathlib.Path(path).write_text("content")

        with patch("debian_cloud_init.cloud_init.ask_yes_no", return_value=True), \
             patch("urllib.request.urlretrieve", side_effect=fake_urlretrieve):
            assert ensure_file_exists(f, download_url="https://example.com/file") is True

    def test_missing_file_with_url_download_fails_exits(self, tmp_path):
        with patch("debian_cloud_init.cloud_init.ask_yes_no", return_value=True), \
             patch("urllib.request.urlretrieve", side_effect=OSError("network error")):
            with pytest.raises(SystemExit):
                ensure_file_exists(tmp_path / "missing.txt", download_url="https://example.com/file")


# =============================================================================
# validate_yaml
# =============================================================================


class TestValidateYaml:
    def test_valid_yaml_passes(self, tmp_path):
        f = tmp_path / "valid.yaml"
        f.write_text("key: value\nlist:\n  - a\n  - b\n")
        validate_yaml(f)

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
# create_meta_data
# =============================================================================


class TestCreateMetaData:
    def test_vmname_used_as_hostname(self, tmp_path):
        with patch("debian_cloud_init.cloud_init.time.time", return_value=12345):
            create_meta_data("myvm", tmp_path)
        content = (tmp_path / "meta-data.yml").read_text()
        assert "local-hostname: myvm" in content
        assert "instance-id: myvm-12345" in content

    def test_instance_id_contains_vmname(self, tmp_path):
        with patch("debian_cloud_init.cloud_init.time.time", return_value=1):
            create_meta_data("special-vm", tmp_path)
        assert "special-vm" in (tmp_path / "meta-data.yml").read_text()

    def test_output_is_valid_yaml(self, tmp_path):
        with patch("debian_cloud_init.cloud_init.time.time", return_value=42):
            create_meta_data("testvm", tmp_path)
        content = (tmp_path / "meta-data.yml").read_text()
        assert yaml.safe_load(content) is not None

    def test_vmname_with_hyphens_and_digits(self, tmp_path):
        with patch("debian_cloud_init.cloud_init.time.time", return_value=1):
            create_meta_data("my-vm-01", tmp_path)
        assert "my-vm-01" in (tmp_path / "meta-data.yml").read_text()

    def test_same_vmname_same_second_same_instance_id(self, tmp_path):
        """Dokumentiert: gleicher vmname + gleiche Sekunde → identische instance-id."""
        with patch("debian_cloud_init.cloud_init.time.time", return_value=1000):
            create_meta_data("vm1", tmp_path)
            first = (tmp_path / "meta-data.yml").read_text()
            create_meta_data("vm1", tmp_path)
            second = (tmp_path / "meta-data.yml").read_text()
        assert "instance-id: vm1-1000" in first
        assert "instance-id: vm1-1000" in second

    def test_different_vmnames_no_collision(self, tmp_path):
        with patch("debian_cloud_init.cloud_init.time.time", return_value=1000):
            create_meta_data("vm1", tmp_path)
            content1 = (tmp_path / "meta-data.yml").read_text()
            create_meta_data("vm2", tmp_path)
            content2 = (tmp_path / "meta-data.yml").read_text()
        assert "instance-id: vm1-1000" in content1
        assert "instance-id: vm2-1000" in content2


# =============================================================================
# create_network_config
# =============================================================================


class TestCreateNetworkConfig:
    def test_debian_returns_none(self):
        assert create_network_config("debian/13", pathlib.Path("/tmp")) is None

    def test_debian_12_returns_none(self):
        assert create_network_config("debian/12", pathlib.Path("/tmp")) is None

    def test_ubuntu_returns_path(self, tmp_path):
        result = create_network_config("ubuntu/24.04", tmp_path)
        assert result is not None
        assert result.exists()

    def test_ubuntu_config_structure(self, tmp_path):
        path = create_network_config("ubuntu/24.04", tmp_path)
        assert path is not None
        cfg = yaml.safe_load(path.read_text())
        assert cfg["version"] == 2
        eth = cfg["ethernets"]["all-en"]
        assert eth["dhcp4"] is True
        assert eth["dhcp6"] is False
        assert eth["match"]["name"] == "en*"

    def test_ubuntu_2204_works(self, tmp_path):
        assert create_network_config("ubuntu/22.04", tmp_path) is not None
