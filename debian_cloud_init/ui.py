import subprocess
import sys
import time
from typing import NoReturn


def progress(msg):
    print(f"\n➡ {msg}")
    time.sleep(0.3)


def success(msg):
    print(f"✔ {msg}")


def fail(msg) -> NoReturn:
    print(f"❌ {msg}")
    sys.exit(1)


def ask_yes_no(question, default=True):
    suffix = "[J/n]" if default else "[j/N]"
    while True:
        ans = input(f"{question} {suffix}: ").strip().lower()
        if not ans:
            return default
        if ans in ["j", "y", "ja", "yes"]:
            return True
        if ans in ["n", "no", "nein"]:
            return False
        print("Bitte mit 'j' für Ja oder 'n' für Nein antworten.")


def run_cmd(cmd):
    print(f"→ {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        fail("Fehler beim Ausführen des Befehls.")
