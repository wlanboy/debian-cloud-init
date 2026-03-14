"""Unit-Tests für session.py"""

import json
from unittest.mock import MagicMock, patch

import pytest

from session import get_or_create_session, load_session, save_session


# =============================================================================
# load_session
# =============================================================================


class TestLoadSession:
    def test_no_file_returns_none(self, tmp_path):
        with patch("session.SESSION_FILE", tmp_path / ".session"):
            result = load_session()
        assert result is None

    def test_valid_json_returns_data(self, tmp_path):
        session_file = tmp_path / ".session"
        data = {"vmname": "testvm", "arch": "amd64", "username": "user"}
        session_file.write_text(json.dumps(data))
        with patch("session.SESSION_FILE", session_file):
            result = load_session()
        assert result == data

    def test_invalid_json_returns_none(self, tmp_path):
        session_file = tmp_path / ".session"
        session_file.write_text("not valid json {{{")
        with patch("session.SESSION_FILE", session_file):
            result = load_session()
        assert result is None

    def test_empty_json_object_returns_empty_dict(self, tmp_path):
        session_file = tmp_path / ".session"
        session_file.write_text("{}")
        with patch("session.SESSION_FILE", session_file):
            result = load_session()
        assert result == {}

    def test_all_session_fields_preserved(self, tmp_path):
        session_file = tmp_path / ".session"
        data = {
            "vmname": "debian13",
            "hostname": "debian13",
            "username": "wlanboy",
            "distro": "debian/13",
            "arch": "amd64",
            "ssh_key": "/home/user/.ssh/id_rsa.pub",
            "hashed_password": "$6$salt$hash",
            "net_type": "default",
            "bridge_interface": None,
        }
        session_file.write_text(json.dumps(data))
        with patch("session.SESSION_FILE", session_file):
            result = load_session()
        assert result == data


# =============================================================================
# save_session
# =============================================================================


class TestSaveSession:
    def test_writes_valid_json(self, tmp_path):
        session_file = tmp_path / ".session"
        data = {"vmname": "myvm", "arch": "amd64"}
        with patch("session.SESSION_FILE", session_file):
            save_session(data)
        loaded = json.loads(session_file.read_text())
        assert loaded == data

    def test_output_is_pretty_printed(self, tmp_path):
        session_file = tmp_path / ".session"
        with patch("session.SESSION_FILE", session_file):
            save_session({"a": 1, "b": 2})
        # indent=4 → Inhalt verteilt sich über mehrere Zeilen
        assert "\n" in session_file.read_text()

    def test_none_values_preserved(self, tmp_path):
        session_file = tmp_path / ".session"
        data = {"bridge_interface": None, "vmname": "vm1"}
        with patch("session.SESSION_FILE", session_file):
            save_session(data)
        loaded = json.loads(session_file.read_text())
        assert loaded["bridge_interface"] is None

    def test_roundtrip_load_after_save(self, tmp_path):
        session_file = tmp_path / ".session"
        original = {"vmname": "roundtrip-vm", "arch": "arm64", "net_type": "bridge"}
        with patch("session.SESSION_FILE", session_file):
            save_session(original)
            result = load_session()
        assert result == original


# =============================================================================
# get_or_create_session – vorhandene Session
# =============================================================================


class TestGetOrCreateSessionExisting:
    def test_existing_session_is_returned(self, tmp_path):
        existing = {
            "vmname": "existing-vm",
            "arch": "amd64",
            "username": "user",
            "distro": "debian/13",
        }
        session_file = tmp_path / ".session"
        session_file.write_text(json.dumps(existing))
        with patch("session.SESSION_FILE", session_file):
            session, is_persistent = get_or_create_session()
        assert is_persistent is True
        assert session["vmname"] == "existing-vm"

    def test_existing_session_flag_is_true(self, tmp_path):
        session_file = tmp_path / ".session"
        session_file.write_text(json.dumps({"vmname": "vm", "arch": "amd64"}))
        with patch("session.SESSION_FILE", session_file):
            _, is_persistent = get_or_create_session()
        assert is_persistent is True

    def test_existing_session_not_modified(self, tmp_path):
        data = {"vmname": "untouched", "distro": "ubuntu/24.04", "arch": "arm64"}
        session_file = tmp_path / ".session"
        session_file.write_text(json.dumps(data))
        with patch("session.SESSION_FILE", session_file):
            session, _ = get_or_create_session()
        assert session["distro"] == "ubuntu/24.04"
        assert session["arch"] == "arm64"


# =============================================================================
# get_or_create_session – neue Session
# =============================================================================


def _setup_ssh_key(tmp_path):
    """Legt ein einzelnes .pub-File in tmp_path/.ssh an."""
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


class TestGetOrCreateSessionNew:
    def test_defaults_produce_debian13_amd64(self, tmp_path):
        session_file = tmp_path / ".session"
        _setup_ssh_key(tmp_path)
        with patch("session.SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=["", "", "", ""]), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("session.ask_yes_no", return_value=False):
            session, is_persistent = get_or_create_session()
        assert is_persistent is False
        assert session["distro"] == "debian/13"
        assert session["arch"] == "amd64"
        assert session["vmname"] == "debian13"
        assert session["username"] == "wlanboy"
        assert session["net_type"] == "default"
        assert session["bridge_interface"] is None

    def test_new_session_saved_to_file(self, tmp_path):
        session_file = tmp_path / ".session"
        _setup_ssh_key(tmp_path)
        with patch("session.SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=["", "", "", ""]), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("session.ask_yes_no", return_value=False):
            get_or_create_session()
        assert session_file.exists()
        data = json.loads(session_file.read_text())
        assert "vmname" in data
        assert "distro" in data

    def test_password_hash_stored_in_session(self, tmp_path):
        session_file = tmp_path / ".session"
        _setup_ssh_key(tmp_path)
        with patch("session.SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=["", "", "", ""]), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("session.ask_yes_no", return_value=False):
            session, _ = get_or_create_session()
        assert session["hashed_password"] == "$6$salt$hashedpassword"

    def test_distro_choice_2_selects_ubuntu_2404(self, tmp_path):
        session_file = tmp_path / ".session"
        _setup_ssh_key(tmp_path)
        # Auswahl [2] = ubuntu/24.04; vmname und username auf Default
        with patch("session.SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=["2", "", "", ""]), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("session.ask_yes_no", return_value=False):
            session, _ = get_or_create_session()
        assert session["distro"] == "ubuntu/24.04"
        assert session["vmname"] == "ubuntu2404"

    def test_arch_choice_1_selects_arm64(self, tmp_path):
        session_file = tmp_path / ".session"
        _setup_ssh_key(tmp_path)
        with patch("session.SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=["", "1", "", ""]), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("session.ask_yes_no", return_value=False):
            session, _ = get_or_create_session()
        assert session["arch"] == "arm64"

    def test_invalid_distro_choice_falls_back_to_default(self, tmp_path):
        session_file = tmp_path / ".session"
        _setup_ssh_key(tmp_path)
        with patch("session.SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=["99", "", "", ""]), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("session.ask_yes_no", return_value=False):
            session, _ = get_or_create_session()
        assert session["distro"] == "debian/13"

    def test_custom_vmname_and_username(self, tmp_path):
        session_file = tmp_path / ".session"
        _setup_ssh_key(tmp_path)
        with patch("session.SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=["", "", "custom-vm", "myuser"]), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("session.ask_yes_no", return_value=False):
            session, _ = get_or_create_session()
        assert session["vmname"] == "custom-vm"
        assert session["username"] == "myuser"

    def test_no_ssh_keys_exits(self, tmp_path):
        session_file = tmp_path / ".session"
        # .ssh-Verzeichnis existiert, aber ohne .pub-Dateien
        (tmp_path / ".ssh").mkdir()
        with patch("session.SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=["", "", "", ""]), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", return_value=_mkpasswd_mock()), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("session.ask_yes_no", return_value=False):
            with pytest.raises(SystemExit):
                get_or_create_session()

    def test_mkpasswd_fails_exits(self, tmp_path):
        session_file = tmp_path / ".session"
        _setup_ssh_key(tmp_path)
        with patch("session.SESSION_FILE", session_file), \
             patch("builtins.input", side_effect=["", "", "", ""]), \
             patch("getpass.getpass", return_value="secret"), \
             patch("subprocess.run", side_effect=Exception("mkpasswd not found")), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("session.ask_yes_no", return_value=False):
            with pytest.raises(SystemExit):
                get_or_create_session()
