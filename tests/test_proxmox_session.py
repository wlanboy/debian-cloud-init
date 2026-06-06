"""Unit-Tests für proxmox_session.py"""

import json
from unittest.mock import MagicMock, patch

import pytest

import debian_cloud_init.proxmox_session as proxmox_session
from debian_cloud_init.proxmox_session import delete_session, get_or_create_session


def _full_session(vmname="testvm"):
    return {
        "proxmox_host": "192.168.1.100",
        "proxmox_ssh_user": "root",
        "proxmox_node": "pve",
        "proxmox_vmid": 100,
        "proxmox_storage": "local-lvm",
        "proxmox_snippets_path": "/var/lib/vz/snippets",
        "proxmox_bridge": "vmbr0",
        "vmname": vmname,
        "username": "wlanboy",
        "distro": "debian/13",
        "arch": "amd64",
        "ssh_key": "/home/user/.ssh/id_rsa.pub",
        "hashed_password": "$6$salt$hash",
    }


def _setup_ssh_key(tmp_path):
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    key = ssh_dir / "id_rsa.pub"
    key.write_text("ssh-rsa AAAAB3NzaC1 user@host")
    return key


def _mkpasswd_mock():
    m = MagicMock()
    m.stdout = "$6$salt$hashedpassword\n"
    m.returncode = 0
    return m


# =============================================================================
# _load_all
# =============================================================================


class TestLoadAll:
    def test_no_file_returns_empty_dict(self, tmp_path):
        with patch.object(proxmox_session, "SESSION_FILE", tmp_path / ".proxmox-session"):
            assert proxmox_session._load_all() == {}

    def test_valid_multisession_json_returned(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        data = {"testvm": _full_session("testvm")}
        session_file.write_text(json.dumps(data))
        with patch.object(proxmox_session, "SESSION_FILE", session_file):
            result = proxmox_session._load_all()
        assert "testvm" in result

    def test_flat_format_migrated_to_multisession(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        session_file.write_text(json.dumps(_full_session("testvm")))
        with patch.object(proxmox_session, "SESSION_FILE", session_file):
            result = proxmox_session._load_all()
        assert "testvm" in result
        assert result["testvm"]["vmname"] == "testvm"

    def test_invalid_json_returns_empty_dict(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        session_file.write_text("not valid json {{{")
        with patch.object(proxmox_session, "SESSION_FILE", session_file):
            assert proxmox_session._load_all() == {}


# =============================================================================
# delete_session
# =============================================================================


class TestDeleteSession:
    def test_existing_vmname_removed(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        session_file.write_text(json.dumps({"testvm": _full_session("testvm")}))
        with patch.object(proxmox_session, "SESSION_FILE", session_file):
            delete_session("testvm")
        data = json.loads(session_file.read_text())
        assert "testvm" not in data

    def test_unknown_vmname_no_error(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        session_file.write_text(json.dumps({"testvm": _full_session("testvm")}))
        with patch.object(proxmox_session, "SESSION_FILE", session_file):
            delete_session("nonexistent")
        data = json.loads(session_file.read_text())
        assert "testvm" in data

    def test_no_file_no_error(self, tmp_path):
        with patch.object(proxmox_session, "SESSION_FILE", tmp_path / ".proxmox-session"):
            delete_session("anyvm")


# =============================================================================
# get_or_create_session – vorhandene Session
# =============================================================================


class TestGetOrCreateSessionExisting:
    def test_existing_session_is_returned(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        session_file.write_text(json.dumps({"testvm": _full_session("testvm")}))
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", return_value=""):
            session, is_persistent = get_or_create_session()
        assert is_persistent is True
        assert session["vmname"] == "testvm"

    def test_existing_session_flag_is_true(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        session_file.write_text(json.dumps({"testvm": _full_session("testvm")}))
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", return_value=""):
            _, is_persistent = get_or_create_session()
        assert is_persistent is True

    def test_existing_session_data_not_modified(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        session_file.write_text(json.dumps({"testvm": _full_session("testvm")}))
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", return_value=""):
            session, _ = get_or_create_session()
        assert session["proxmox_host"] == "192.168.1.100"
        assert session["distro"] == "debian/13"
        assert session["arch"] == "amd64"

    def test_flat_format_migration_then_select(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        session_file.write_text(json.dumps(_full_session("testvm")))
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", return_value=""):
            session, is_persistent = get_or_create_session()
        assert is_persistent is True
        assert session["vmname"] == "testvm"

    def test_invalid_selection_falls_back_to_first(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        session_file.write_text(json.dumps({"testvm": _full_session("testvm")}))
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", return_value="99"):
            session, _ = get_or_create_session()
        assert session["vmname"] == "testvm"


# =============================================================================
# get_or_create_session – neue Session erstellen
# =============================================================================


class TestGetOrCreateSessionNew:
    # _create_session input order:
    # 1. proxmox_host, 2. ssh_user, 3. node, 4. vmid,
    # 5. storage, 6. snippets_path, 7. bridge,
    # 8. distro_choice, 9. arch_choice, 10. vmname, 11. username
    _DEFAULTS = ["192.168.1.100", "", "", "100", "", "", "", "", "", "", ""]

    def test_defaults_produce_debian13_amd64(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        _setup_ssh_key(tmp_path)
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=list(self._DEFAULTS)), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path):
            session, is_persistent = get_or_create_session()
        assert is_persistent is False
        assert session["distro"] == "debian/13"
        assert session["arch"] == "amd64"
        assert session["vmname"] == "debian13"
        assert session["username"] == "wlanboy"

    def test_proxmox_connection_defaults_stored(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        _setup_ssh_key(tmp_path)
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=list(self._DEFAULTS)), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path):
            session, _ = get_or_create_session()
        assert session["proxmox_host"] == "192.168.1.100"
        assert session["proxmox_ssh_user"] == "root"
        assert session["proxmox_node"] == "pve"
        assert session["proxmox_vmid"] == 100
        assert session["proxmox_storage"] == "local-lvm"
        assert session["proxmox_bridge"] == "vmbr0"

    def test_session_saved_in_multisession_format(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        _setup_ssh_key(tmp_path)
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=list(self._DEFAULTS)), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path):
            get_or_create_session()
        data = json.loads(session_file.read_text())
        assert "debian13" in data
        inner = data["debian13"]
        assert "vmname" in inner
        assert "distro" in inner

    def test_ubuntu_distro_choice(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        _setup_ssh_key(tmp_path)
        inputs = ["192.168.1.100", "", "", "100", "", "", "", "2", "", "", ""]
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=inputs), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path):
            session, _ = get_or_create_session()
        assert session["distro"] == "ubuntu/24.04"
        assert session["vmname"] == "ubuntu2404"

    def test_arm64_arch_choice(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        _setup_ssh_key(tmp_path)
        inputs = ["192.168.1.100", "", "", "100", "", "", "", "", "1", "", ""]
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=inputs), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path):
            session, _ = get_or_create_session()
        assert session["arch"] == "arm64"

    def test_custom_vmname_and_username(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        _setup_ssh_key(tmp_path)
        inputs = ["192.168.1.100", "", "", "100", "", "", "", "", "", "custom-vm", "myuser"]
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=inputs), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path):
            session, _ = get_or_create_session()
        assert session["vmname"] == "custom-vm"
        assert session["username"] == "myuser"

    def test_missing_host_exits(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        _setup_ssh_key(tmp_path)
        inputs = ["", "", "", "100", "", "", "", "", "", "", ""]
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=inputs), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path):
            with pytest.raises(SystemExit):
                get_or_create_session()

    def test_invalid_vmid_exits(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        _setup_ssh_key(tmp_path)
        inputs = ["192.168.1.100", "", "", "abc", "", "", "", "", "", "", ""]
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=inputs), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path):
            with pytest.raises(SystemExit):
                get_or_create_session()

    def test_no_ssh_keys_exits(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        (tmp_path / ".ssh").mkdir()
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=list(self._DEFAULTS)), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path):
            with pytest.raises(SystemExit):
                get_or_create_session()

    def test_mkpasswd_fails_exits(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        _setup_ssh_key(tmp_path)
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=list(self._DEFAULTS)), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", side_effect=Exception("mkpasswd not found")), \
             patch("pathlib.Path.home", return_value=tmp_path):
            with pytest.raises(SystemExit):
                get_or_create_session()

    def test_duplicate_vmname_exits(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        session_file.write_text(json.dumps({"debian13": _full_session("debian13")}))
        _setup_ssh_key(tmp_path)
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=list(self._DEFAULTS) + [""]), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("builtins.input", side_effect=["n"] + list(self._DEFAULTS)):
            with pytest.raises(SystemExit):
                get_or_create_session()


# =============================================================================
# _import_session
# =============================================================================


class TestImportSession:
    # _import_session input order:
    # 1. proxmox_host, 2. ssh_user, 3. node, 4. storage, 5. snippets_path,
    # 6. bridge, 7. vmid, 8. vmname, 9. username, 10. distro_choice, 11. arch
    _DEFAULTS = ["192.168.1.100", "", "", "", "", "", "200", "imported-vm", "", "", ""]

    def test_import_returns_is_persistent_true(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        _setup_ssh_key(tmp_path)
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=list(self._DEFAULTS)), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("debian_cloud_init.proxmox_session.ask_yes_no", return_value=False):
            _, is_persistent = proxmox_session._import_session({})
        assert is_persistent is True

    def test_import_session_defaults(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        _setup_ssh_key(tmp_path)
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=list(self._DEFAULTS)), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("debian_cloud_init.proxmox_session.ask_yes_no", return_value=False):
            session, _ = proxmox_session._import_session({})
        assert session["proxmox_host"] == "192.168.1.100"
        assert session["proxmox_vmid"] == 200
        assert session["vmname"] == "imported-vm"
        assert session["proxmox_ssh_user"] == "root"
        assert session["distro"] == "debian/13"
        assert session["arch"] == "amd64"

    def test_import_empty_vmname_exits(self, tmp_path):
        _setup_ssh_key(tmp_path)
        inputs = ["192.168.1.100", "", "", "", "", "", "200", "", "", "", ""]
        with patch("builtins.input", side_effect=inputs), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("debian_cloud_init.proxmox_session.ask_yes_no", return_value=False):
            with pytest.raises(SystemExit):
                proxmox_session._import_session({})

    def test_import_invalid_vmid_exits(self, tmp_path):
        _setup_ssh_key(tmp_path)
        inputs = ["192.168.1.100", "", "", "", "", "", "abc", "myvm", "", "", ""]
        with patch("builtins.input", side_effect=inputs), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("debian_cloud_init.proxmox_session.ask_yes_no", return_value=False):
            with pytest.raises(SystemExit):
                proxmox_session._import_session({})

    def test_import_duplicate_vmname_exits(self, tmp_path):
        _setup_ssh_key(tmp_path)
        existing = {"imported-vm": _full_session("imported-vm")}
        inputs = ["192.168.1.100", "", "", "", "", "", "200", "imported-vm", "", "", ""]
        with patch("builtins.input", side_effect=inputs), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("debian_cloud_init.proxmox_session.ask_yes_no", return_value=False):
            with pytest.raises(SystemExit):
                proxmox_session._import_session(existing)

    def test_import_empty_host_exits(self, tmp_path):
        _setup_ssh_key(tmp_path)
        inputs = ["", "", "", "", "", "", "200", "myvm", "", "", ""]
        with patch("builtins.input", side_effect=inputs), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("debian_cloud_init.proxmox_session.ask_yes_no", return_value=False):
            with pytest.raises(SystemExit):
                proxmox_session._import_session({})

    def test_import_no_ssh_keys_exits(self, tmp_path):
        (tmp_path / ".ssh").mkdir()
        inputs = list(self._DEFAULTS)
        with patch("builtins.input", side_effect=inputs), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("debian_cloud_init.proxmox_session.ask_yes_no", return_value=False):
            with pytest.raises(SystemExit):
                proxmox_session._import_session({})

    def test_import_saved_to_file(self, tmp_path):
        session_file = tmp_path / ".proxmox-session"
        _setup_ssh_key(tmp_path)
        with patch.object(proxmox_session, "SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=list(self._DEFAULTS)), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("debian_cloud_init.proxmox_session.ask_yes_no", return_value=False):
            proxmox_session._import_session({})
        data = json.loads(session_file.read_text())
        assert "imported-vm" in data


# =============================================================================
# _sync_sessions
# =============================================================================


def _ssh_ok():
    m = MagicMock()
    m.returncode = 0
    m.stdout = "status: stopped"
    return m


def _ssh_missing():
    m = MagicMock()
    m.returncode = 1
    m.stdout = ""
    return m


class TestSyncSessions:
    def test_all_found_returns_sessions_unchanged(self):
        sessions = {"vm1": _full_session("vm1"), "vm2": _full_session("vm2")}
        with patch("debian_cloud_init.proxmox.ssh_run", return_value=_ssh_ok()):
            result = proxmox_session._sync_sessions(sessions)
        assert "vm1" in result
        assert "vm2" in result

    def test_all_missing_user_confirms_returns_empty(self, tmp_path):
        sessions = {"vm1": _full_session("vm1"), "vm2": _full_session("vm2")}
        session_file = tmp_path / ".proxmox-session"
        session_file.write_text(json.dumps(sessions))
        with patch("debian_cloud_init.proxmox.ssh_run", return_value=_ssh_missing()), \
             patch("debian_cloud_init.proxmox_session.ask_yes_no", return_value=True), \
             patch.object(proxmox_session, "SESSION_FILE", session_file):
            result = proxmox_session._sync_sessions(sessions)
        assert result == {}

    def test_all_missing_user_declines_sessions_unchanged(self, tmp_path):
        sessions = {"vm1": _full_session("vm1"), "vm2": _full_session("vm2")}
        session_file = tmp_path / ".proxmox-session"
        session_file.write_text(json.dumps(sessions))
        with patch("debian_cloud_init.proxmox.ssh_run", return_value=_ssh_missing()), \
             patch("debian_cloud_init.proxmox_session.ask_yes_no", return_value=False), \
             patch.object(proxmox_session, "SESSION_FILE", session_file):
            result = proxmox_session._sync_sessions(sessions)
        assert "vm1" in result
        assert "vm2" in result

    def test_partial_missing_only_missing_removed(self, tmp_path):
        sessions = {"existing": _full_session("existing"), "gone": _full_session("gone")}
        session_file = tmp_path / ".proxmox-session"
        session_file.write_text(json.dumps(sessions))
        with patch("debian_cloud_init.proxmox.ssh_run",
                   side_effect=[_ssh_ok(), _ssh_missing()]), \
             patch("debian_cloud_init.proxmox_session.ask_yes_no", return_value=True), \
             patch.object(proxmox_session, "SESSION_FILE", session_file):
            result = proxmox_session._sync_sessions(sessions)
        assert "existing" in result
        assert "gone" not in result

    def test_deleted_sessions_removed_from_file(self, tmp_path):
        sessions = {"vm1": _full_session("vm1")}
        session_file = tmp_path / ".proxmox-session"
        session_file.write_text(json.dumps(sessions))
        with patch("debian_cloud_init.proxmox.ssh_run", return_value=_ssh_missing()), \
             patch("debian_cloud_init.proxmox_session.ask_yes_no", return_value=True), \
             patch.object(proxmox_session, "SESSION_FILE", session_file):
            proxmox_session._sync_sessions(sessions)
        data = json.loads(session_file.read_text())
        assert "vm1" not in data

    def test_empty_sessions_returns_empty(self):
        with patch("debian_cloud_init.proxmox.ssh_run") as mock_ssh:
            result = proxmox_session._sync_sessions({})
        mock_ssh.assert_not_called()
        assert result == {}
