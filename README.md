# debian kvm cloud init

## get debian image
Do not use genericcloud images, they do not contain sata ahci drivers for cloud init.
```
cd /isos
wget https://cdimage.debian.org/cdimage/cloud/bookworm/latest/debian-12-generic-amd64.qcow2
wget https://cdimage.debian.org/cdimage/cloud/trixie/latest/debian-13-generic-amd64.qcow2
```

## sources for images
- https://cdimage.debian.org/cdimage/cloud/
- https://cloud-images.ubuntu.com/noble/current/

## create cloud init
```bash
sudo apt-get install whois # to get mkpasswd binary
mkpasswd -m sha-512 # to generate hash for your user password

cp cloud-init.yml /isos # copy cloud-init.yaml with inserted values
```

## check supported os variant list
```bash
virt-install --os-variant list

virsh net-start host-bridge # check if host-bridge is running
```

## Create base hard disk image and install debian with cloud init with debian 12
```bash
qemu-img create -f qcow2 -o backing_file=/isos/debian-12-generic-amd64.qcow2,backing_fmt=qcow2 /isos/debian-12.qcow2 30G # create disk image for vm

virt-install \
  --name debian12 \
  --memory 4096 \
  --vcpus 4\
  --disk /isos/debian-12.qcow2,device=disk,bus=virtio \
  --os-variant debian12 \
  --virt-type kvm \
  --graphics none \
  --console pty,target_type=serial \
  --network network=default,model=virtio \
  --network bridge=virbr0,model=virtio \
  --cloud-init user-data=/isos/cloud-init.yml \
  --import
```

## Create base hard disk image and install debian with cloud init with debian 13 (needs uefi)
```bash
qemu-img create -f qcow2 -o backing_file=/isos/debian-13-generic-amd64.qcow2,backing_fmt=qcow2 /isos/debian-13.qcow2 30G # create disk image for vm

virt-install \
  --name debian13 \
  --memory 4096 \
  --vcpus 4\
  --disk /isos/debian-13.qcow2,device=disk,bus=virtio \
  --os-variant debian13 \
  --virt-type kvm \
  --graphics none \
  --console pty,target_type=serial \
  --network network=default,model=virtio \
  --cloud-init user-data=/isos/cloud-init.yml \
  --boot uefi \
  --import
```

## cloud init tools
### check cloud-init status
```bash
sudo journalctl -u cloud-init
sudo cat /var/log/cloud-init.log
```

### trigger cloud init
```bash
sudo cloud-init clean
sudo cloud-init init
sudo cloud-init modules --mode=config
sudo cloud-init modules --mode=final
```