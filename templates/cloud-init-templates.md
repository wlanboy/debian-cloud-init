# Templates

Dieser Ordner enthält die Bausteine, aus denen `generator.py` (lokales KVM/libvirt)
und `proxmox_generator.py` (Proxmox) zur Laufzeit die finale `cloud-init.yml`
zusammensetzen. Keine dieser Dateien wird direkt verwendet – sie werden geladen,
kombiniert und als neues YAML geschrieben.

## cloud-init-template.yml
Basis-Skelett der Cloud-Init-Konfiguration (`#cloud-config`). Enthält nur leere
Platzhalter für `users` und `runcmd`. Diese werden vom Python-Skript zur Laufzeit
überschrieben:
- `users` → wird mit Username, gehashtem Passwort, SSH-Key und
  Sudo-Rechten (`NOPASSWD:ALL`) befüllt.
- `runcmd` → wird aus `package-config.txt` (als einzelne Befehle) plus dem
  kompletten Inhalt von `amd64-tools.sh` und `system-config.txt` (als
  Literal-Blöcke) zusammengesetzt.

## package-config.txt
Liste einzelner Shell-Befehle (eine Zeile = ein `runcmd`-Eintrag). Wird
Zeile für Zeile eingelesen, leere Zeilen werden übersprungen. Aktuell:
Docker-Repository einrichten (Keyring anlegen, GPG-Key laden, `apt`-Quelle
für `docker-ce` eintragen, `apt-get update`).

## system-config.txt
Wird als ganzer Block (Shell-Skript) in `runcmd` eingebettet. Installiert
Basis-Pakete (`nano`, `htop`, `git`, `qemu-guest-agent`, …) sowie Docker
selbst, fügt den Standard-User (UID 1000) zur `docker`-Gruppe hinzu, aktiviert
IP-Forwarding, deaktiviert Swap dauerhaft, stellt `iptables`/`ip6tables` auf
Legacy-Modus um und aktiviert den `qemu-guest-agent`-Dienst.

## amd64-tools.sh
Optionales Zusatzskript, ebenfalls als Block in `runcmd` eingebettet. Installiert
gängige Kubernetes-/DevOps-Tools für `amd64`: `kubectl`, `helm`, `kind`, `istioctl`,
`k9s`, `argocd` und den Lasttest-Client `hey`. Versionsnummern stehen als
Variablen am Anfang des Skripts.

Falls die Datei lokal fehlt, wird sie automatisch von
`https://github.com/wlanboy/vagrantkind/raw/refs/heads/main/amd64-tools.sh`
heruntergeladen (siehe `ensure_file_exists()` in `generator.py` /
`proxmox_generator.py`).

## Ablauf beim Zusammenbau
1. `cloud-init-template.yml` wird geparst.
2. `users` wird mit den Session-/CLI-Parametern befüllt.
3. `runcmd` = Zeilen aus `package-config.txt` + Inhalt von `amd64-tools.sh`
   + Inhalt von `system-config.txt` (jeweils als literaler Mehrzeilen-Block).
4. Das Ergebnis wird als `cloud-init.yml` im Projektroot bzw. nach `/isos`
   geschrieben und per YAML-Validierung geprüft.

Wer zusätzliche Pakete oder eigene Provisioning-Schritte braucht, trägt sie
einfach in `package-config.txt` bzw. `system-config.txt` ein – eine Anpassung
des Python-Codes ist dafür nicht nötig.
