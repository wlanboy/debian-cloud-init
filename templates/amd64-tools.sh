#!/bin/bash
set -e
cd ~

curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x ./kubectl
sudo cp ./kubectl /usr/local/bin

# see https://github.com/helm/helm/releases
HELM_VERSION="3.19.2"
# see https://github.com/kubernetes-sigs/kind/releases/
KIND_VERSION="0.30.0"
# see https://github.com/istio/istio/releases/
ISTIO_VERSION="1.28.2"
# see https://github.com/derailed/k9s/releases
K9S_VERSION="0.50.16"
ARGOCD_VERSION="v3.2.2"
#see https://github.com/argoproj/argo-cd/releases

cd ~
wget "https://get.helm.sh/helm-v${HELM_VERSION}-linux-amd64.tar.gz"
tar -zxvf "helm-v${HELM_VERSION}-linux-amd64.tar.gz"
sudo cp linux-amd64/helm /usr/local/bin/helm
sudo install -m 555 linux-amd64/helm /usr/local/bin/khelmind
rm "helm-v${HELM_VERSION}-linux-amd64.tar.gz"
rm -Rf linux-amd64

curl -Lo ./kind "https://kind.sigs.k8s.io/dl/v${KIND_VERSION}/kind-linux-amd64"
chmod +x ./kind
sudo install -m 555 kind /usr/local/bin/kind
rm kind

wget "https://github.com/istio/istio/releases/download/${ISTIO_VERSION}/istio-${ISTIO_VERSION}-linux-amd64.tar.gz"
tar -zxvf "istio-${ISTIO_VERSION}-linux-amd64.tar.gz"
sudo install -m 555 "istio-${ISTIO_VERSION}/bin/istioctl" /usr/local/bin/istioctl
rm "istio-${ISTIO_VERSION}-linux-amd64.tar.gz"

wget "https://github.com/derailed/k9s/releases/download/v${K9S_VERSION}/k9s_Linux_amd64.tar.gz"
tar -zxvf k9s_Linux_amd64.tar.gz
sudo install -m 555 k9s /usr/local/bin/k9s
rm k9s_Linux_amd64.tar.gz

curl -sSL -o argocd-linux-amd64 https://github.com/argoproj/argo-cd/releases/download/${ARGOCD_VERSION}/argocd-linux-amd64
sudo install -m 555 argocd-linux-amd64 /usr/local/bin/argocd
rm argocd-linux-amd64

wget https://hey-release.s3.us-east-2.amazonaws.com/hey_linux_amd64
sudo install -m 555 hey_linux_amd64 /usr/local/bin/hey
rm hey_linux_amd64
