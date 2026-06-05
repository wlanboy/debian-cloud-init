"""Unit-Tests für vm.py"""

from unittest.mock import MagicMock, patch

import pytest

from vm import (
    _image_info,
    _os_variant,
    create_seed_iso,
    delete_vm,
    ensure_base_image,
    ensure_isos_folder,
    ensure_overlay_image,
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

    def test_missing_slash_raises(self):
        with pytest.raises((ValueError, IndexError)):
            _os_variant("debian")

    def test_ubuntu_starts_with_ubuntu(self):
        assert _os_variant("ubuntu/22.04").startswith("ubuntu")

    def test_debian_starts_with_debian(self):
        assert _os_variant("debian/12").startswith("debian")


# =============================================================================
# _image_info
# =============================================================================


class TestImageInfo:
    def test_ubuntu_amd64(self):
        name, url = _image_info("ubuntu/24.04", "amd64")
        assert name == "ubuntu-24.04-server-cloudimg-amd64.img"
        assert url.startswith("https://cloud-images.ubuntu.com")
        assert "amd64" in url

    def test_ubuntu_arm64(self):
        name, url = _image_info("ubuntu/22.04", "arm64")
        assert name == "ubuntu-22.04-server-cloudimg-arm64.img"
        assert "arm64" in url

    def test_debian_13_uses_trixie(self):
        name, url = _image_info("debian/13", "amd64")
        assert name == "debian-13-generic-amd64.qcow2"
        assert "trixie" in url
        assert url.startswith("https://cdimage.debian.org")

    def test_debian_12_uses_bookworm(self):
        _, url = _image_info("debian/12", "amd64")
        assert "bookworm" in url

    def test_debian_arm64(self):
        name, url = _image_info("debian/13", "arm64")
        assert "arm64" in name
        assert "arm64" in url

    def test_missing_slash_raises(self):
        with pytest.raises((ValueError, IndexError)):
            _image_info("ubuntu", "amd64")

    def test_unknown_debian_version_falls_back_to_bookworm(self):
        """Dokumentiert den Bug: Debian 14+ wird fälschlich als 'bookworm' aufgelöst."""
        _, url = _image_info("debian/14", "amd64")
        assert "bookworm" in url

    def test_ubuntu_url_ends_with_img(self):
        _, url = _image_info("ubuntu/24.04", "amd64")
        assert url.endswith(".img")

    def test_debian_url_ends_with_qcow2(self):
        _, url = _image_info("debian/13", "amd64")
        assert url.endswith(".qcow2")


# =============================================================================
# ensure_isos_folder
# =============================================================================


class TestEnsureIsosFolder:
    def _mock_path(self, exists, st_uid=1000, st_gid=2000):
        mock = MagicMock()
        mock.exists.return_value = exists
        mock.stat.return_value = MagicMock(st_uid=st_uid, st_gid=st_gid)
        return mock

    def test_exists_correct_permissions_returns_silently(self):
        mock_path = self._mock_path(exists=True, st_uid=1000, st_gid=2000)
        with patch("vm.ISOS_PATH", mock_path), \
             patch("vm.os.getuid", return_value=1000), \
             patch("vm.grp.getgrnam", return_value=MagicMock(gr_gid=2000)):
            ensure_isos_folder()  # kein SystemExit

    def test_exists_wrong_uid_user_confirms_chown(self):
        mock_path = self._mock_path(exists=True, st_uid=999, st_gid=2000)
        with patch("vm.ISOS_PATH", mock_path), \
             patch("vm.os.getuid", return_value=1000), \
             patch("vm.grp.getgrnam", return_value=MagicMock(gr_gid=2000)), \
             patch("vm.ask_yes_no", return_value=True), \
             patch("vm.run_cmd") as mock_run_cmd, \
             patch("vm.os.getlogin", return_value="testuser"):
            ensure_isos_folder()
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "chown" in calls

    def test_exists_wrong_permissions_user_declines_exits(self):
        mock_path = self._mock_path(exists=True, st_uid=999, st_gid=2000)
        with patch("vm.ISOS_PATH", mock_path), \
             patch("vm.os.getuid", return_value=1000), \
             patch("vm.grp.getgrnam", return_value=MagicMock(gr_gid=2000)), \
             patch("vm.ask_yes_no", return_value=False):
            with pytest.raises(SystemExit):
                ensure_isos_folder()

    def test_not_exists_user_confirms_creates_folder(self):
        mock_path = self._mock_path(exists=False)
        with patch("vm.ISOS_PATH", mock_path), \
             patch("vm.ask_yes_no", return_value=True), \
             patch("vm.run_cmd") as mock_run_cmd:
            ensure_isos_folder()
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "mkdir" in calls

    def test_not_exists_user_declines_exits(self):
        mock_path = self._mock_path(exists=False)
        with patch("vm.ISOS_PATH", mock_path), \
             patch("vm.ask_yes_no", return_value=False):
            with pytest.raises(SystemExit):
                ensure_isos_folder()


# =============================================================================
# ensure_base_image
# =============================================================================


class TestEnsureBaseImage:
    def test_image_exists_returns_silently(self, tmp_path):
        (tmp_path / "debian-13-generic-amd64.qcow2").write_text("fake")
        with patch("vm.ISOS_PATH", tmp_path):
            ensure_base_image("amd64", "debian/13")

    def test_image_missing_user_confirms_runs_wget(self, tmp_path):
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("vm.ask_yes_no", return_value=True), \
             patch("vm.run_cmd") as mock_run_cmd:
            ensure_base_image("amd64", "debian/13")
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "wget" in calls
        assert "debian-13-generic-amd64.qcow2" in calls

    def test_image_missing_user_declines_exits(self, tmp_path):
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("vm.ask_yes_no", return_value=False):
            with pytest.raises(SystemExit):
                ensure_base_image("amd64", "debian/13")

    def test_ubuntu_image_name_in_wget_call(self, tmp_path):
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("vm.ask_yes_no", return_value=True), \
             patch("vm.run_cmd") as mock_run_cmd:
            ensure_base_image("amd64", "ubuntu/24.04")
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "ubuntu-24.04-server-cloudimg-amd64.img" in calls

    def test_arm64_image_name_in_wget_call(self, tmp_path):
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("vm.ask_yes_no", return_value=True), \
             patch("vm.run_cmd") as mock_run_cmd:
            ensure_base_image("arm64", "debian/13")
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "arm64" in calls


# =============================================================================
# ensure_overlay_image
# =============================================================================


class TestEnsureOverlayImage:
    def test_no_overlay_no_base_exits(self, tmp_path):
        with patch("vm.ISOS_PATH", tmp_path):
            with pytest.raises(SystemExit):
                ensure_overlay_image("myvm", "amd64", "debian/13")

    def test_base_exists_creates_overlay_via_qemu_img(self, tmp_path):
        (tmp_path / "debian-13-generic-amd64.qcow2").write_text("fake base")
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("vm.run_cmd") as mock_run_cmd:
            ensure_overlay_image("myvm", "amd64", "debian/13")
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "qemu-img" in calls
        assert "myvm.qcow2" in calls

    def test_qemu_img_uses_30g_size(self, tmp_path):
        (tmp_path / "debian-13-generic-amd64.qcow2").write_text("fake base")
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("vm.run_cmd") as mock_run_cmd:
            ensure_overlay_image("myvm", "amd64", "debian/13")
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "30G" in calls

    def test_overlay_exists_user_confirms_recreate(self, tmp_path):
        (tmp_path / "debian-13-generic-amd64.qcow2").write_text("fake base")
        (tmp_path / "myvm.qcow2").write_text("old overlay")
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("vm.ask_yes_no", return_value=True), \
             patch("vm.run_cmd") as mock_run_cmd:
            ensure_overlay_image("myvm", "amd64", "debian/13")
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "qemu-img" in calls

    def test_overlay_exists_user_declines_no_qemu_call(self, tmp_path):
        (tmp_path / "myvm.qcow2").write_text("old overlay")
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("vm.ask_yes_no", return_value=False), \
             patch("vm.run_cmd") as mock_run_cmd:
            ensure_overlay_image("myvm", "amd64", "debian/13")
        mock_run_cmd.assert_not_called()


# =============================================================================
# create_seed_iso
# =============================================================================


class TestCreateSeedIso:
    def _setup_isos(self, tmp_path):
        (tmp_path / "cloud-init.yml").write_text("#cloud-config\n{}")
        (tmp_path / "meta-data.yml").write_text("instance-id: test\n")

    def test_returns_correct_path(self, tmp_path):
        self._setup_isos(tmp_path)
        with patch("vm.ISOS_PATH", tmp_path), patch("vm.run_cmd"):
            result = create_seed_iso("myvm")
        assert result == tmp_path / "myvm-seed.iso"

    def test_genisoimage_called(self, tmp_path):
        self._setup_isos(tmp_path)
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("vm.run_cmd") as mock_run_cmd:
            create_seed_iso("myvm")
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "genisoimage" in calls

    def test_without_network_config_no_network_config_arg(self, tmp_path):
        self._setup_isos(tmp_path)
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("vm.run_cmd") as mock_run_cmd:
            create_seed_iso("myvm")
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "network-config" not in calls

    def test_with_network_config_included_in_iso(self, tmp_path):
        self._setup_isos(tmp_path)
        net_cfg = tmp_path / "network-config.yml"
        net_cfg.write_text("version: 2\n")
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("vm.run_cmd") as mock_run_cmd:
            create_seed_iso("myvm", network_config_file=net_cfg)
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "network-config" in calls

    def test_cidata_volid_set(self, tmp_path):
        self._setup_isos(tmp_path)
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("vm.run_cmd") as mock_run_cmd:
            create_seed_iso("myvm")
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "cidata" in calls


# =============================================================================
# delete_vm
# =============================================================================


class TestDeleteVm:
    def test_vm_not_found_returns_silently(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=1)), \
             patch("vm.time.sleep"):
            delete_vm("nonexistent-vm")

    def test_vm_exists_user_declines_exits(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("vm.ask_yes_no", return_value=False), \
             patch("vm.time.sleep"):
            with pytest.raises(SystemExit):
                delete_vm("myvm")

    def test_vm_exists_user_confirms_calls_undefine(self, tmp_path):
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("vm.ask_yes_no", return_value=True), \
             patch("vm.run_cmd") as mock_run_cmd, \
             patch("vm.time.sleep"):
            delete_vm("myvm")
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "undefine" in calls

    def test_skip_confirm_bypasses_question(self, tmp_path):
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("vm.run_cmd") as mock_run_cmd, \
             patch("vm.time.sleep"):
            delete_vm("myvm", skip_confirm=True)
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "undefine" in calls

    def test_overlay_deleted_when_exists(self, tmp_path):
        (tmp_path / "myvm.qcow2").write_text("fake image")
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("vm.run_cmd") as mock_run_cmd, \
             patch("vm.time.sleep"):
            delete_vm("myvm", skip_confirm=True)
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "myvm.qcow2" in calls

    def test_seed_iso_deleted_when_exists(self, tmp_path):
        (tmp_path / "myvm-seed.iso").write_text("fake iso")
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("vm.run_cmd") as mock_run_cmd, \
             patch("vm.time.sleep"):
            delete_vm("myvm", skip_confirm=True)
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "myvm-seed.iso" in calls

    def test_no_extra_files_no_rm_calls(self, tmp_path):
        with patch("vm.ISOS_PATH", tmp_path), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("vm.run_cmd") as mock_run_cmd, \
             patch("vm.time.sleep"):
            delete_vm("myvm", skip_confirm=True)
        calls = " ".join(str(c) for c in mock_run_cmd.call_args_list)
        assert "rm -f" not in calls
