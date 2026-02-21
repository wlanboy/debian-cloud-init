tests/test_utils.py (41 Tests)

Klasse	Was wird getestet
TestOsVariant	_os_variant() für debian/ubuntu, verschiedene Versionen
TestImageInfo	_image_info() — Dateiname + URL für alle Distro/Arch-Kombinationen
TestAskYesNo	Alle Eingaben (j/y/ja/yes/n/no/nein), Defaults, Großschreibung, Retry bei ungültiger Eingabe
TestEnsureFileExists	Datei vorhanden, fehlt ohne URL, fehlt mit URL (Ablehnen → Exit, Download OK, Download Fehler)
TestValidateYaml	Valides YAML, leeres YAML, kaputtes YAML → SystemExit
TestLiteralString	Ist str-Subklasse, YAML-Ausgabe nutzt Literal-Block-Stil (|)
TestCreateNetworkConfig	Debian → None, Ubuntu → Datei mit korrekter Netplan-Struktur
TestCreateMetaData	Hostname-Fallback auf vmname, expliziter Hostname, instance-id
tests/test_session.py (12 Tests)

Klasse	Was wird getestet
TestLoadSession	Kein File → None, valides JSON, ungültiges JSON, leeres JSON, alle Felder erhalten
TestSaveSession	Schreibt valides JSON, Pretty-Print mit indent=4, None-Werte, Roundtrip
TestGetOrCreateSessionExisting	Gibt vorhandene Session zurück, is_persistent=True, Daten unverändert