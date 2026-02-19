# debian/ubuntu kvm virsh install with cloud init
This repo describes how to auto install Debian 12, Debian 13, Ubuntu 22.04 and Ubuntu 24.04 with virsh-install and cloud-init.
Which images you can use, and which images you should not use.
How to add user passwords with hashes and how to create harddisk images from templates.

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

python3 generator.py
# or
uv run generator.py
```

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
