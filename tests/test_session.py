"""Unit-Tests für session.py"""

import json
from unittest.mock import patch


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
