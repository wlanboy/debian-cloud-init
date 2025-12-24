# debian kvm virsh install with cloud init
This repo describes how to auto install debain12 and debian13 with virsh-install and cloud-init.
Which images you can use, and which images you should not use.
How to add user passwords with hashes and how to create harddisk images from templates.

## sources for images
- https://cdimage.debian.org/cdimage/cloud/
- https://cloud-images.ubuntu.com/noble/current/

## get debian image
Do not use genericcloud images, they do not contain sata ahci drivers for cloud init.
```
cd /isos
wget https://cdimage.debian.org/cdimage/cloud/bookworm/latest/debian-12-generic-amd64.qcow2
wget https://cdimage.debian.org/cdimage/cloud/trixie/latest/debian-13-generic-amd64.qcow2
```

## prepare cloud init file
This python script asks for username, password, list all public ssh keys to select one.
It uses this information to update the cloud-init.yml template.
It needs mkpasswd (packaged with whois) to create the hash for the user password.
```bash
sudo apt-get install whois # to get mkpasswd binary

python3 cloud-init-generator.py
```

## create cloud init
```bash
mkpasswd -m sha-512 # to generate hash for your user password
cp cloud-init.yml /isos # copy cloud-init.yaml with inserted values
```

## check supported os variant list
```bash
virt-install --os-variant list

virsh net-start host-bridge # check if host-bridge is running
```

## Create base hard disk image and install debian12 with cloud init
```bash
# create disk image for vm
qemu-img create -f qcow2 -o backing_file=/isos/debian-12-generic-amd64.qcow2,backing_fmt=qcow2 /isos/debian-12.qcow2 30G 

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

## Create base hard disk image and install debian13 with cloud init (needs uefi)
```bash
# create disk image for vm
qemu-img create -f qcow2 -o backing_file=/isos/debian-13-generic-amd64.qcow2,backing_fmt=qcow2 /isos/debian-13.qcow2 30G

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

## if install works for your usecase add following parameter for background install
```
virt-install \
...
--noautoconsole \
```

## delete vms
```bash
virsh shutdown debian12
virsh destroy debian12
virsh undefine debian12

virsh shutdown debian13
virsh destroy debian13
virsh undefine debian13
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