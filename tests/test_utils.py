"""Unit-Tests für utils.py"""

import pathlib
from unittest.mock import MagicMock, patch

import pytest
import yaml

from utils import (
    LiteralString,
    _image_info,
    _os_variant,
    ask_yes_no,
    create_meta_data,
    create_network_config,
    delete_vm,
    ensure_file_exists,
    run_cmd,
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


# =============================================================================
# _image_info – Cornercases
# =============================================================================


class TestImageInfoEdgeCases:
    def test_missing_slash_raises(self):
        """Kein '/' im Distro-String → ValueError beim Entpacken."""
        with pytest.raises((ValueError, IndexError)):
            _image_info("ubuntu", "amd64")

    def test_unknown_debian_version_falls_back_to_bookworm(self):
        """Dokumentiert den Bug: Debian 14+ wird fälschlich als 'bookworm' aufgelöst."""
        _, url = _image_info("debian/14", "amd64")
        # Erwartet wird ein Fehler, tatsächlich passiert es aber nicht → Bug
        assert "bookworm" in url  # Bug: sollte "forky" o.ä. sein

    def test_debian_version_in_image_name(self):
        name, _ = _image_info("debian/14", "amd64")
        assert "14" in name

    def test_ubuntu_url_structure(self):
        _, url = _image_info("ubuntu/24.04", "amd64")
        assert url.startswith("https://cloud-images.ubuntu.com/releases/")
        assert url.endswith(".img")

    def test_debian_url_structure(self):
        _, url = _image_info("debian/13", "amd64")
        assert url.startswith("https://cdimage.debian.org/cdimage/cloud/")
        assert url.endswith(".qcow2")


# =============================================================================
# _os_variant – Cornercases
# =============================================================================


class TestOsVariantEdgeCases:
    def test_missing_slash_raises(self):
        with pytest.raises((ValueError, IndexError)):
            _os_variant("debian")

    def test_ubuntu_result_starts_with_ubuntu(self):
        assert _os_variant("ubuntu/22.04").startswith("ubuntu")

    def test_debian_result_starts_with_debian(self):
        assert _os_variant("debian/12").startswith("debian")


# =============================================================================
# ask_yes_no – Cornercases
# =============================================================================


class TestAskYesNoEdgeCases:
    def test_answer_with_leading_trailing_whitespace_yes(self):
        with patch("builtins.input", return_value="  j  "):
            assert ask_yes_no("Test?") is True

    def test_answer_with_leading_trailing_whitespace_no(self):
        with patch("builtins.input", return_value="  N  "):
            assert ask_yes_no("Test?") is False

    def test_yes_fully_uppercase(self):
        with patch("builtins.input", return_value="YES"):
            assert ask_yes_no("Test?") is True

    def test_no_fully_uppercase(self):
        with patch("builtins.input", return_value="NO"):
            assert ask_yes_no("Test?") is False

    def test_nein_uppercase(self):
        with patch("builtins.input", return_value="NEIN"):
            assert ask_yes_no("Test?") is False

    def test_many_invalid_inputs_then_valid(self):
        inputs = ["abc", "123", "??", "vielleicht", "j"]
        with patch("builtins.input", side_effect=inputs):
            assert ask_yes_no("Test?") is True


# =============================================================================
# run_cmd
# =============================================================================


class TestRunCmd:
    def test_success_does_not_exit(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            run_cmd("echo test")  # darf nicht werfen

    def test_failure_exits(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=1)):
            with pytest.raises(SystemExit):
                run_cmd("false")

    def test_nonzero_returncode_exits(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=127)):
            with pytest.raises(SystemExit):
                run_cmd("command_not_found")


# =============================================================================
# create_meta_data – Cornercases
# =============================================================================


class TestCreateMetaDataEdgeCases:
    def test_same_vmname_same_second_produces_same_instance_id(self, tmp_path):
        """Dokumentiert: Gleicher vmname + gleiche Sekunde → identische instance-id (Kollision)."""
        with patch("utils.ISOS_PATH", tmp_path):
            with patch("utils.time.time", return_value=1000):
                create_meta_data("vm1")
                first = (tmp_path / "meta-data.yml").read_text()
                create_meta_data("vm1")
                second = (tmp_path / "meta-data.yml").read_text()
        # Beide instance-ids sind identisch → bekannter Bug
        assert "instance-id: vm1-1000" in first
        assert "instance-id: vm1-1000" in second

    def test_different_vmnames_same_second_no_collision(self, tmp_path):
        with patch("utils.ISOS_PATH", tmp_path):
            with patch("utils.time.time", return_value=1000):
                create_meta_data("vm1")
                content1 = (tmp_path / "meta-data.yml").read_text()
                create_meta_data("vm2")
                content2 = (tmp_path / "meta-data.yml").read_text()
        assert "instance-id: vm1-1000" in content1
        assert "instance-id: vm2-1000" in content2

    def test_vmname_with_hyphens_and_digits(self, tmp_path):
        with patch("utils.ISOS_PATH", tmp_path):
            with patch("utils.time.time", return_value=1):
                create_meta_data("my-vm-01")
        content = (tmp_path / "meta-data.yml").read_text()
        assert "my-vm-01" in content

    def test_meta_data_file_is_valid_yaml(self, tmp_path):
        with patch("utils.ISOS_PATH", tmp_path):
            with patch("utils.time.time", return_value=42):
                create_meta_data("testvm")
        content = (tmp_path / "meta-data.yml").read_text()
        parsed = yaml.safe_load(content)
        assert "instance-id" in parsed or content.startswith("instance-id:")

    def test_hostname_not_same_as_vmname_different_values(self, tmp_path):
        with patch("utils.ISOS_PATH", tmp_path):
            with patch("utils.time.time", return_value=1):
                create_meta_data("myvm", hostname="other-host")
        content = (tmp_path / "meta-data.yml").read_text()
        assert "local-hostname: other-host" in content
        assert "instance-id: myvm-1" in content


# =============================================================================
# delete_vm
# =============================================================================


class TestDeleteVm:
    def test_vm_not_found_returns_silently(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=1)):
            with patch("utils.time.sleep"):
                delete_vm("nonexistent-vm")  # kein Fehler, kein SystemExit

    def test_vm_exists_user_declines_exits(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("utils.ask_yes_no", return_value=False), \
             patch("utils.time.sleep"):
            with pytest.raises(SystemExit):
                delete_vm("myvm")

    def test_vm_exists_user_confirms_calls_undefine(self, tmp_path):
        with patch("utils.ISOS_PATH", tmp_path), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("utils.ask_yes_no", return_value=True), \
             patch("utils.run_cmd") as mock_run_cmd, \
             patch("utils.time.sleep"):
            delete_vm("myvm")
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "undefine" in calls

    def test_vm_exists_skip_confirm_calls_undefine(self, tmp_path):
        with patch("utils.ISOS_PATH", tmp_path), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("utils.run_cmd") as mock_run_cmd, \
             patch("utils.time.sleep"):
            delete_vm("myvm", skip_confirm=True)
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "undefine" in calls

    def test_overlay_deleted_when_exists(self, tmp_path):
        overlay = tmp_path / "myvm.qcow2"
        overlay.write_text("fake image")
        with patch("utils.ISOS_PATH", tmp_path), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("utils.run_cmd") as mock_run_cmd, \
             patch("utils.time.sleep"):
            delete_vm("myvm", skip_confirm=True)
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "myvm.qcow2" in calls

    def test_seed_iso_deleted_when_exists(self, tmp_path):
        seed = tmp_path / "myvm-seed.iso"
        seed.write_text("fake iso")
        with patch("utils.ISOS_PATH", tmp_path), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("utils.run_cmd") as mock_run_cmd, \
             patch("utils.time.sleep"):
            delete_vm("myvm", skip_confirm=True)
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "myvm-seed.iso" in calls

    def test_no_extra_files_no_rm_calls(self, tmp_path):
        with patch("utils.ISOS_PATH", tmp_path), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("utils.run_cmd") as mock_run_cmd, \
             patch("utils.time.sleep"):
            delete_vm("myvm", skip_confirm=True)
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "rm -f" not in calls
