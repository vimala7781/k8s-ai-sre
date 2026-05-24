# Phase 1 Setup — Step by Step (Windows 11 Home)

Follow each step in order. Do not skip ahead.
Every step has a verification command — only move forward when it passes.

---

## Step 1 — Enable WSL2

Open PowerShell as Administrator (right-click Start → "Windows PowerShell (Admin)")
then run:

```powershell
wsl --install
```

This installs WSL2 and Ubuntu in one command. It will ask you to restart your machine.
After restart, Ubuntu will open and ask you to create a Linux username and password.
Set anything you like — write it down, you'll need it.

**Verify:**
```powershell
wsl --status
```
You should see: `Default Version: 2`

---

## Step 2 — Install Docker Desktop

1. Download from: https://www.docker.com/products/docker-desktop/
2. Run the installer — keep all defaults, make sure "Use WSL2 instead of Hyper-V" is checked
3. After install, open Docker Desktop and wait for it to say "Engine running" in the bottom left

**Verify — open a new PowerShell (normal, not admin):**
```powershell
docker --version
```
You should see something like: `Docker version 26.x.x`

```powershell
docker run hello-world
```
You should see: `Hello from Docker!`
This confirms Docker can pull and run a container end to end.

---

## Step 3 — Install kubectl

kubectl is the command line tool you already know. Install it via winget (built into Windows 11):

```powershell
winget install Kubernetes.kubectl
```

Close and reopen PowerShell after this.

**Verify:**
```powershell
kubectl version --client
```
You should see a version number printed.

---

## Step 4 — Install Minikube

```powershell
winget install Kubernetes.minikube
```

Close and reopen PowerShell after this.

**Verify:**
```powershell
minikube version
```

---

## Step 5 — Start your Kubernetes cluster

This is the moment. Run:

```powershell
minikube start --driver=docker
```

First time takes 3-5 minutes — it downloads the Kubernetes node image.
You'll see a progress bar. When it says "Done! kubectl is now configured" you're in.

**Verify:**
```powershell
kubectl get nodes
```

Expected output:
```
NAME       STATUS   ROLES           AGE   VERSION
minikube   Ready    control-plane   1m    v1.xx.x
```

STATUS must be `Ready`. If it says `NotReady` wait 30 seconds and run again.

---

## Step 6 — Create the project namespace

A namespace is like a folder inside Kubernetes — it keeps our project's pods separate
from anything else running in the cluster.

```powershell
kubectl create namespace k8s-ai-sre
```

**Verify:**
```powershell
kubectl get namespaces
```

You should see `k8s-ai-sre` in the list.

---

## You are done with Step 1 setup.

Come back to Claude and paste the output of:
```powershell
kubectl get nodes
kubectl get namespaces
```

That's the Phase 1 exit check for this step.
