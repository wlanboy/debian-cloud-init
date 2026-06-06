"""Unit-Tests für proxmox.py"""

from unittest.mock import MagicMock, patch

import pytest

from debian_cloud_init.proxmox import (
    _extract_ip_from_interfaces,
    create_vm,
    delete_vm,
    ensure_base_image,
    upload_snippets,
)


# =============================================================================
# _extract_ip_from_interfaces
# =============================================================================


def _iface(name, ip, ip_type="ipv4"):
    return {"name": name, "ip-addresses": [{"ip-address-type": ip_type, "ip-address": ip}]}


class TestExtractIpFromInterfaces:
    def test_direct_list_returns_first_ipv4(self):
        assert _extract_ip_from_interfaces([_iface("eth0", "192.168.1.10")]) == "192.168.1.10"

    def test_result_wrapper_dict(self):
        assert _extract_ip_from_interfaces({"result": [_iface("eth0", "10.0.0.5")]}) == "10.0.0.5"

    def test_data_wrapper_dict(self):
        assert _extract_ip_from_interfaces({"data": [_iface("eth0", "10.0.0.6")]}) == "10.0.0.6"

    def test_loopback_interface_skipped(self):
        data = [_iface("lo", "127.0.0.1"), _iface("eth0", "192.168.1.20")]
        assert _extract_ip_from_interfaces(data) == "192.168.1.20"

    def test_127x_address_skipped(self):
        data = [{"name": "eth0", "ip-addresses": [{"ip-address-type": "ipv4", "ip-address": "127.0.0.1"}]}]
        assert _extract_ip_from_interfaces(data) is None

    def test_ipv6_address_skipped(self):
        assert _extract_ip_from_interfaces([_iface("eth0", "::1", ip_type="ipv6")]) is None

    def test_empty_list_returns_none(self):
        assert _extract_ip_from_interfaces([]) is None

    def test_empty_result_wrapper_returns_none(self):
        assert _extract_ip_from_interfaces({"result": []}) is None

    def test_non_dict_non_list_returns_none(self):
        assert _extract_ip_from_interfaces("invalid") is None
        assert _extract_ip_from_interfaces(42) is None

    def test_multiple_interfaces_returns_first_non_lo(self):
        data = [_iface("lo", "127.0.0.1"), _iface("eth0", "192.168.1.10"), _iface("eth1", "10.0.0.1")]
        assert _extract_ip_from_interfaces(data) == "192.168.1.10"

    def test_no_ip_addresses_key_skipped(self):
        assert _extract_ip_from_interfaces([{"name": "eth0"}]) is None

    def test_empty_ip_address_string_skipped(self):
        data = [{"name": "eth0", "ip-addresses": [{"ip-address-type": "ipv4", "ip-address": ""}]}]
        assert _extract_ip_from_interfaces(data) is None


# =============================================================================
# delete_vm
# =============================================================================


def _ssh_result(returncode=0, stdout=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    return m


class TestDeleteVm:
    def test_vm_not_found_returns_silently(self):
        with patch("debian_cloud_init.proxmox.ssh_run", return_value=_ssh_result(returncode=1)):
            delete_vm("host", "root", 100, "testvm")

    def test_vm_exists_skip_confirm_calls_destroy(self):
        with patch("debian_cloud_init.proxmox.ssh_run", return_value=_ssh_result()) as mock_ssh:
            delete_vm("host", "root", 100, "testvm", skip_confirm=True)
        calls = " ".join(str(c) for c in mock_ssh.call_args_list)
        assert "destroy" in calls

    def test_vm_exists_user_confirms_calls_stop_then_destroy(self):
        with patch("debian_cloud_init.proxmox.ssh_run", return_value=_ssh_result()) as mock_ssh, \
             patch("debian_cloud_init.proxmox.ask_yes_no", return_value=True):
            delete_vm("host", "root", 100, "testvm")
        calls = " ".join(str(c) for c in mock_ssh.call_args_list)
        assert "stop" in calls
        assert "destroy" in calls

    def test_vm_exists_user_declines_exits(self):
        with patch("debian_cloud_init.proxmox.ssh_run", return_value=_ssh_result()), \
             patch("debian_cloud_init.proxmox.ask_yes_no", return_value=False):
            with pytest.raises(SystemExit):
                delete_vm("host", "root", 100, "testvm")

    def test_vmid_included_in_destroy_call(self):
        with patch("debian_cloud_init.proxmox.ssh_run", return_value=_ssh_result()) as mock_ssh:
            delete_vm("host", "root", 999, "testvm", skip_confirm=True)
        calls = " ".join(str(c) for c in mock_ssh.call_args_list)
        assert "999" in calls


# =============================================================================
# ensure_base_image
# =============================================================================


class TestEnsureBaseImage:
    def test_image_exists_returns_path_with_filename(self):
        with patch("debian_cloud_init.proxmox.ssh_run", return_value=_ssh_result(returncode=0)):
            path = ensure_base_image("host", "root", "amd64", "debian/13")
        assert "debian-13-generic-amd64.qcow2" in path

    def test_image_exists_no_download_attempted(self):
        with patch("debian_cloud_init.proxmox.ssh_run", return_value=_ssh_result(returncode=0)) as mock_ssh:
            ensure_base_image("host", "root", "amd64", "debian/13")
        calls = " ".join(str(c) for c in mock_ssh.call_args_list)
        assert "wget" not in calls

    def test_image_missing_user_confirms_downloads(self):
        with patch("debian_cloud_init.proxmox.ssh_run", side_effect=[
            _ssh_result(returncode=1),
            _ssh_result(),
        ]) as mock_ssh, \
             patch("debian_cloud_init.proxmox.ask_yes_no", return_value=True):
            ensure_base_image("host", "root", "amd64", "debian/13")
        calls = " ".join(str(c) for c in mock_ssh.call_args_list)
        assert "wget" in calls

    def test_image_missing_user_declines_exits(self):
        with patch("debian_cloud_init.proxmox.ssh_run", return_value=_ssh_result(returncode=1)), \
             patch("debian_cloud_init.proxmox.ask_yes_no", return_value=False):
            with pytest.raises(SystemExit):
                ensure_base_image("host", "root", "amd64", "debian/13")

    def test_ubuntu_image_name_in_returned_path(self):
        with patch("debian_cloud_init.proxmox.ssh_run", return_value=_ssh_result(returncode=0)):
            path = ensure_base_image("host", "root", "amd64", "ubuntu/24.04")
        assert "ubuntu-24.04-server-cloudimg-amd64.img" in path

    def test_arm64_image_name_in_returned_path(self):
        with patch("debian_cloud_init.proxmox.ssh_run", return_value=_ssh_result(returncode=0)):
            path = ensure_base_image("host", "root", "arm64", "debian/13")
        assert "arm64" in path


# =============================================================================
# upload_snippets
# =============================================================================


class TestUploadSnippets:
    def test_scp_called_three_times(self, tmp_path):
        cloud_init_yml = tmp_path / "cloud-init.yml"
        cloud_init_yml.write_text("#cloud-config\n{}")
        with patch("debian_cloud_init.proxmox.ssh_run"), \
             patch("debian_cloud_init.proxmox.scp_to") as mock_scp:
            upload_snippets("host", "root", "/var/lib/vz/snippets", "testvm", cloud_init_yml)
        assert mock_scp.call_count == 3

    def test_user_data_source_is_cloud_init_yml(self, tmp_path):
        cloud_init_yml = tmp_path / "cloud-init.yml"
        cloud_init_yml.write_text("#cloud-config\n{}")
        with patch("debian_cloud_init.proxmox.ssh_run"), \
             patch("debian_cloud_init.proxmox.scp_to") as mock_scp:
            upload_snippets("host", "root", "/var/lib/vz/snippets", "testvm", cloud_init_yml)
        first_src = mock_scp.call_args_list[0].args[2]
        assert first_src == cloud_init_yml

    def test_all_three_snippet_files_named_correctly(self, tmp_path):
        cloud_init_yml = tmp_path / "cloud-init.yml"
        cloud_init_yml.write_text("#cloud-config\n{}")
        with patch("debian_cloud_init.proxmox.ssh_run"), \
             patch("debian_cloud_init.proxmox.scp_to") as mock_scp:
            upload_snippets("host", "root", "/var/lib/vz/snippets", "myvm", cloud_init_yml)
        destinations = [str(c.args[3]) for c in mock_scp.call_args_list]
        assert any("myvm-user-data.yml" in d for d in destinations)
        assert any("myvm-meta-data.yml" in d for d in destinations)
        assert any("myvm-network-config.yml" in d for d in destinations)

    def test_mkdir_called_for_snippets_path(self, tmp_path):
        cloud_init_yml = tmp_path / "cloud-init.yml"
        cloud_init_yml.write_text("#cloud-config\n{}")
        with patch("debian_cloud_init.proxmox.ssh_run") as mock_ssh, \
             patch("debian_cloud_init.proxmox.scp_to"):
            upload_snippets("host", "root", "/var/lib/vz/snippets", "testvm", cloud_init_yml)
        calls = " ".join(str(c) for c in mock_ssh.call_args_list)
        assert "mkdir" in calls


# =============================================================================
# create_vm
# =============================================================================


def _make_ssh_result(returncode=0, stdout=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    return m


def _ssh_config_side_effect(*args, **kwargs):
    cmd = args[2]
    if "qm config" in cmd:
        return _make_ssh_result(stdout="unused0: local-lvm:vm-100-disk-0\n")
    return _make_ssh_result()


def _create_vm_call(tmp_path, ask_yes_no_side_effect, ask_int_side_effect=None):
    cloud_init_yml = tmp_path / "cloud-init.yml"
    cloud_init_yml.write_text("#cloud-config\n{}")
    int_patch = patch("debian_cloud_init.proxmox.ask_int", side_effect=ask_int_side_effect or [])
    with patch("debian_cloud_init.proxmox.upload_snippets"), \
         patch("debian_cloud_init.proxmox.ensure_base_image", return_value="/images/debian.qcow2"), \
         patch("debian_cloud_init.proxmox.ask_yes_no", side_effect=ask_yes_no_side_effect), \
         patch("debian_cloud_init.proxmox.ssh_run", side_effect=_ssh_config_side_effect) as mock_ssh, \
         int_patch:
        create_vm("host", "root", "pve", 100, "testvm", "amd64", "debian/13",
                  "local-lvm", "vmbr0", "/var/lib/vz/snippets", cloud_init_yml)
    return mock_ssh


class TestCreateVm:
    def test_skipped_when_user_declines(self, tmp_path):
        cloud_init_yml = tmp_path / "cloud-init.yml"
        cloud_init_yml.write_text("#cloud-config\n{}")
        with patch("debian_cloud_init.proxmox.upload_snippets"), \
             patch("debian_cloud_init.proxmox.ensure_base_image", return_value="/images/debian.qcow2"), \
             patch("debian_cloud_init.proxmox.ask_yes_no", return_value=False), \
             patch("debian_cloud_init.proxmox.ssh_run") as mock_ssh:
            create_vm("host", "root", "pve", 100, "testvm", "amd64", "debian/13",
                      "local-lvm", "vmbr0", "/var/lib/vz/snippets", cloud_init_yml)
        calls = " ".join(str(c) for c in mock_ssh.call_args_list)
        assert "qm create" not in calls

    def test_default_size_uses_4096_memory(self, tmp_path):
        # ask_yes_no: [create VM=True, use defaults=True]
        mock_ssh = _create_vm_call(tmp_path, ask_yes_no_side_effect=[True, True])
        calls = " ".join(str(c) for c in mock_ssh.call_args_list)
        assert "--memory 4096" in calls

    def test_default_size_uses_2_cores(self, tmp_path):
        mock_ssh = _create_vm_call(tmp_path, ask_yes_no_side_effect=[True, True])
        calls = " ".join(str(c) for c in mock_ssh.call_args_list)
        assert "--cores 2" in calls

    def test_default_size_resizes_to_30g(self, tmp_path):
        mock_ssh = _create_vm_call(tmp_path, ask_yes_no_side_effect=[True, True])
        calls = " ".join(str(c) for c in mock_ssh.call_args_list)
        assert "30G" in calls

    def test_custom_size_uses_provided_memory(self, tmp_path):
        # ask_yes_no: [create VM=True, use defaults=False]
        # ask_int: [cores=4, memory=8192, disk=50]
        mock_ssh = _create_vm_call(
            tmp_path,
            ask_yes_no_side_effect=[True, False],
            ask_int_side_effect=[4, 8192, 50],
        )
        calls = " ".join(str(c) for c in mock_ssh.call_args_list)
        assert "--memory 8192" in calls

    def test_custom_size_uses_provided_cores(self, tmp_path):
        mock_ssh = _create_vm_call(
            tmp_path,
            ask_yes_no_side_effect=[True, False],
            ask_int_side_effect=[4, 8192, 50],
        )
        calls = " ".join(str(c) for c in mock_ssh.call_args_list)
        assert "--cores 4" in calls

    def test_custom_size_resizes_to_provided_disk(self, tmp_path):
        mock_ssh = _create_vm_call(
            tmp_path,
            ask_yes_no_side_effect=[True, False],
            ask_int_side_effect=[4, 8192, 50],
        )
        calls = " ".join(str(c) for c in mock_ssh.call_args_list)
        assert "50G" in calls
