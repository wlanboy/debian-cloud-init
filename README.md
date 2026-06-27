# debian/ubuntu cloud init installer

This repository provides a complete workflow for automated installation of Debian 12/13 and Ubuntu 22.04/24.04 using cloud-init.
It supports both local KVM/libvirt environments and remote Proxmox servers, making it ideal for homelabs, DevOps automation, and reproducible VM provisioning.

It explains which cloud images work reliably, which ones should be avoided, and how to configure users, SSH keys, and password hashes.
The project also demonstrates how to generate custom disk images from templates for fast and consistent VM deployment.

A key component is the Python-based TUI, which guides you step-by-step through:

- Selecting the distribution
- Choosing the correct cloud image
- Adding SSH keys and password hashes
- Generating cloud-init configuration
- Creating QCOW2 disk images
- Deploying to KVM/libvirt or Proxmox

This makes cloud-init–based VM provisioning accessible even for users without prior experience.

## screen recordings of tool
![Create VM](./vm_setup.gif)
![Recreate VM](./vm_setup_rebuild.gif)

## sources for images
- https://cdimage.debian.org/cdimage/cloud/
- https://cloud-images.ubuntu.com/noble/current/

## get images
Do not use genericcloud images, they do not contain sata ahci drivers for cloud init.
```
cd /isos

# Debian
wget https://cdimage.debian.org/cdimage/cloud/bookworm/latest/debian-12-generic-amd64.qcow2
wget https://cdimage.debian.org/cdimage/cloud/trixie/latest/debian-13-generic-amd64.qcow2

# Ubuntu
wget https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04-server-cloudimg-amd64.img
wget https://cloud-images.ubuntu.com/releases/22.04/release/ubuntu-22.04-server-cloudimg-amd64.img
```

The generator can also download missing base images automatically on first run.

## prepare cloud init file
This python script manages the full VM lifecycle:
- First run: asks for distro, architecture, VM name, username, password, SSH key and network type
- Saves parameters to a `.session` file for subsequent runs
- Subsequent runs: detects existing VM, offers to show IP or recreate it
- Automatically generates `cloud-init.yml`, `meta-data.yml` and copies them to `/isos`
- For Ubuntu: additionally creates a seed ISO (`genisoimage`) and a `network-config.yml`
- Creates the overlay disk image and runs `virt-install`

It needs `mkpasswd` (packaged with `whois`) and `genisoimage` to work.
```bash
sudo apt-get install whois genisoimage
```

### install as wheel (recommended)
```bash
# build
uv build

# install globally
uv tool install dist/debian_cloud_init-0.1.0-py3-none-any.whl

# run from any directory containing a templates/ folder
debian-cloud-init

# uninstall
uv tool uninstall debian-cloud-init

# reinstall after rebuild
uv tool install --force dist/debian_cloud_init-0.1.0-py3-none-any.whl
```

### run without installing
```bash
uv run debian-cloud-init
# or
uv run python -m debian_cloud_init.generator
```

### oneline mode
Fragt alle Parameter interaktiv ab und gibt am Ende den fertigen Einzeiler-Befehl aus — inklusive gehashtem Passwort. Den Befehl kannst du dann direkt kopieren und ausführen.

```bash
uv run python -m debian_cloud_init.generator --oneline
```

Beispiel-Ausgabe:
```
uv run python -m debian_cloud_init.generator --vmname=debian13 --username=wlanboy --distro=debian/13 --arch=amd64 --ssh-key=/home/user/.ssh/id_rsa.pub --hashed-password='$6$...' --net-type=default
```

### alle parameter direkt übergeben
Wenn alle Pflicht-Parameter als Flags übergeben werden, wird die Session übersprungen und die VM direkt erstellt:

```bash
uv run python -m debian_cloud_init.generator \
  --vmname=debian13 \
  --username=wlanboy \
  --distro=debian/13 \
  --arch=amd64 \
  --ssh-key=~/.ssh/id_rsa.pub \
  --hashed-password='$6$...' \
  --net-type=default

# mit Bridge-Netzwerk:
uv run python -m debian_cloud_init.generator \
  --vmname=debian13 \
  --username=wlanboy \
  --distro=debian/13 \
  --arch=amd64 \
  --ssh-key=~/.ssh/id_rsa.pub \
  --hashed-password='$6$...' \
  --net-type=bridge \
  --bridge-interface=eth0
```

| Parameter | Werte | Beschreibung |
|-----------|-------|-------------|
| `--vmname` | beliebig | Name der VM |
| `--username` | beliebig | Benutzername in der VM |
| `--distro` | `debian/13`, `debian/12`, `ubuntu/24.04`, `ubuntu/22.04` | Distro und Version |
| `--arch` | `amd64`, `arm64` | Ziel-Architektur |
| `--ssh-key` | Pfad | Pfad zum öffentlichen SSH-Key (`.pub`) |
| `--hashed-password` | SHA-512-Hash | Hash via `mkpasswd -m sha-512` |
| `--net-type` | `default`, `bridge` | Netzwerktyp (NAT oder Bridge) |
| `--bridge-interface` | z.B. `eth0` | Bridge-Interface (nur bei `--net-type=bridge`) |

### supported distributions and architectures
| Distro | Version | amd64 | arm64 |
|--------|---------|-------|-------|
| Debian | 12 | ✔ | ✔ |
| Debian | 13 | ✔ | ✔ |
| Ubuntu | 22.04 | ✔ | ✔ |
| Ubuntu | 24.04 | ✔ | ✔ |

### templates
The `templates/` directory contains files that are merged into the generated `cloud-init.yml`:
- `cloud-init-template.yml` – base template (users and runcmd are overwritten by the generator)
- `package-config.txt` – list of runcmd lines to execute (one per line)
- `system-config.txt` – shell script injected as a runcmd block
- `amd64-tools.sh` – additional tooling script (downloaded automatically if missing)

---

## Proxmox (remote server)

The Proxmox backend runs all operations remotely via SSH — the cloud image is downloaded directly on the Proxmox host, and cloud-init snippets are uploaded via SCP. No large file transfers to your local machine.

### prerequisites

**On your local machine:**
- SSH key-based access to the Proxmox host must be set up:
  ```bash
  ssh-copy-id root@<proxmox-host>
  ```
- `mkpasswd` must be installed:
  ```bash
  sudo apt-get install whois
  ```

**On the Proxmox host:**
- The `local` storage must have the **Snippets** content type enabled:
  Datacenter → Storage → local → Edit → check **Snippets**
- `qemu-guest-agent` should be installed in the VM template or via cloud-init `packages` so that IP detection works after boot.

### run

```bash
uv run debian-cloud-init-proxmox
# or after installing as wheel:
debian-cloud-init-proxmox
```

The first run asks for all parameters interactively and saves them to `.proxmox-session`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| Proxmox Host | — | IP or hostname of the Proxmox server |
| SSH User | `root` | SSH user on Proxmox |
| Node Name | `pve` | Proxmox node name |
| VM ID | — | Numeric VM ID (e.g. `100`) |
| Storage Pool | `local-lvm` | Storage pool for disk and cloud-init drive |
| Snippets Path | `/var/lib/vz/snippets` | Path for cloud-init snippet files on Proxmox |
| Network Bridge | `vmbr0` | Bridge interface for the VM network |
| Distro / Arch | `debian/13`, `amd64` | Same options as KVM backend |
| VM Name, User, Password, SSH Key | — | Same as KVM backend |

Subsequent runs detect the existing VM and offer to show the IP or recreate it.

### what happens on each run

1. `cloud-init.yml` is generated locally from the `templates/` directory
2. `user-data` and `meta-data` are uploaded via SCP to the snippets directory on Proxmox
3. The cloud image is downloaded directly on the Proxmox host (into `/var/lib/vz/template/iso/`) if not already present
4. `qm create` → `qm importdisk` → disk attached as `scsi0` → resized to 30 GB
5. Cloud-init drive (`ide2`) added, `--cicustom` pointed at the uploaded snippets
6. VM is started; IP is retrieved via `pvesh` + qemu-guest-agent

### install as wheel

```bash
uv build
uv tool install dist/debian_cloud_init-0.1.0-py3-none-any.whl
debian-cloud-init-proxmox
```

### manual Proxmox commands (reference)

```bash
# import a cloud image manually
qm create 100 --name debian13 --memory 4096 --cores 2 --net0 virtio,bridge=vmbr0
qm importdisk 100 /var/lib/vz/template/iso/debian-13-generic-amd64.qcow2 local-lvm --format qcow2
qm set 100 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-100-disk-0
qm set 100 --ide2 local-lvm:cloudinit
qm set 100 --cicustom "user=local:snippets/myvm-user-data.yml,meta=local:snippets/myvm-meta-data.yml"
qm set 100 --boot order=scsi0
qm resize 100 scsi0 30G
qm start 100

# delete a vm
qm stop 100
qm destroy 100 --destroy-unreferenced-disks 1 --purge 1

# get IP via guest agent
pvesh get /nodes/pve/qemu/100/agent/network-get-interfaces --output-format json
```

---

## create cloud init without tool
```bash
mkpasswd -m sha-512 # to generate hash for your user password
cp cloud-init.yml /isos/cloud-init.yml
```

### check supported os variant list
```bash
virt-install --os-variant list

virsh net-start default # check if default network is running
```

### Create base hard disk image and install debian13 with cloud init
```bash
# create overlay disk image
qemu-img create -f qcow2 -F qcow2 -o backing_file=/isos/debian-13-generic-amd64.qcow2 /isos/debian13.qcow2 30G

virt-install \
  --name debian13 \
  --arch x86_64 \
  --machine q35 \
  --cpu host-passthrough \
  --memory 4096 \
  --vcpus 2 \
  --disk /isos/debian13.qcow2,device=disk,bus=virtio \
  --os-variant debian13 \
  --virt-type kvm \
  --graphics none \
  --console pty,target_type=serial \
  --network network=default,model=virtio \
  --cloud-init user-data=/isos/cloud-init.yml,meta-data=/isos/meta-data.yml \
  --boot uefi \
  --noautoconsole \
  --import
```

### Create base hard disk image and install Ubuntu 24.04 with cloud init
Ubuntu requires a seed ISO instead of `--cloud-init` due to EFI + IDE CDROM incompatibility.
```bash
# create overlay disk image
qemu-img create -f qcow2 -F qcow2 -o backing_file=/isos/ubuntu-24.04-server-cloudimg-amd64.img /isos/ubuntu2404.qcow2 30G

# create seed ISO (user-data = cloud-init.yml, meta-data = meta-data.yml, network-config = network-config.yml)
genisoimage -output /isos/ubuntu2404-seed.iso -volid cidata -joliet -rock \
  /isos/cloud-init.yml /isos/meta-data.yml /isos/network-config.yml

virt-install \
  --name ubuntu2404 \
  --arch x86_64 \
  --machine q35 \
  --cpu host-passthrough \
  --memory 4096 \
  --vcpus 2 \
  --disk /isos/ubuntu2404.qcow2,device=disk,bus=virtio \
  --disk /isos/ubuntu2404-seed.iso,device=cdrom,bus=scsi \
  --os-variant ubuntu24.04 \
  --virt-type kvm \
  --graphics none \
  --console pty,target_type=serial \
  --network network=default,model=virtio \
  --boot uefi \
  --noautoconsole \
  --import
```

### delete vms
```bash
virsh destroy debian13
virsh undefine debian13 --remove-all-storage --nvram

virsh destroy ubuntu2404
virsh undefine ubuntu2404 --remove-all-storage --nvram
```

### cloud init tools
#### check cloud-init status
```bash
sudo journalctl -u cloud-init
sudo cat /var/log/cloud-init.log
```

#### trigger cloud init
```bash
sudo cloud-init clean
sudo cloud-init init
sudo cloud-init modules --mode=config
sudo cloud-init modules --mode=final
```
