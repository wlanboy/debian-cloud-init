"""Unit-Tests für ui.py"""

from unittest.mock import MagicMock, patch

import pytest

from ui import ask_yes_no, fail, run_cmd


# =============================================================================
# fail
# =============================================================================


class TestFail:
    def test_exits_with_nonzero(self):
        with pytest.raises(SystemExit) as exc_info:
            fail("something went wrong")
        assert exc_info.value.code != 0


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

    def test_whitespace_trimmed_yes(self):
        with patch("builtins.input", return_value="  j  "):
            assert ask_yes_no("Test?") is True

    def test_whitespace_trimmed_no(self):
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
        with patch("builtins.input", side_effect=["abc", "123", "??", "vielleicht", "j"]):
            assert ask_yes_no("Test?") is True


# =============================================================================
# run_cmd
# =============================================================================


class TestRunCmd:
    def test_success_does_not_exit(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            run_cmd("echo test")

    def test_failure_exits(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=1)):
            with pytest.raises(SystemExit):
                run_cmd("false")

    def test_nonzero_returncode_exits(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=127)):
            with pytest.raises(SystemExit):
                run_cmd("command_not_found")
