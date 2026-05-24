# Phase 1 — Kubernetes Cluster Setup

## Goal
Get a local Kubernetes cluster running on Windows 11 Home, deploy a healthy pod,
and be able to trigger four failure states on demand.

## Stack decisions

| Tool | Why |
|---|---|
| WSL2 | Built into Windows 11. Provides the Linux kernel containers need. |
| Docker Desktop | Free. Uses WSL2. Minikube uses it as its driver. |
| Minikube | Runs a full Kubernetes cluster inside a Docker container locally. |
| kubectl | Standard Kubernetes CLI. Same commands you'd use on a real cluster. |
| Namespace: k8s-ai-sre | Isolates project resources from any other cluster workloads. |

## Architecture

```
Windows 11 Home
└── WSL2 (Linux kernel)
    └── Docker Desktop
        └── Minikube cluster (docker driver)
            └── namespace: k8s-ai-sre
                ├── healthy-nginx (Deployment)
                └── failure pods (crash-loop, oom, imagepull, missing-secret)
```

## Mini-milestones

### M1.1 — Cluster running
- WSL2 enabled
- Docker Desktop installed and engine running
- kubectl installed
- Minikube started with `--driver=docker`
- `kubectl get nodes` shows STATUS: Ready

### M1.2 — Healthy pod
- `manifests/healthy/healthy-pod.yaml` applied
- Pod shows Running status
- `kubectl logs` returns nginx startup lines

### M1.3 — Failure simulations
All four failure manifests applied and confirmed:

| Pod name | Expected STATUS | Key field in describe |
|---|---|---|
| crash-loop-pod | CrashLoopBackOff | Exit Code: 1 |
| oom-pod | OOMKilled | Exit Code: 137, Reason: OOMKilled |
| imagepull-pod | ImagePullBackOff | Events: image not found |
| missing-secret-pod | Pending | Events: secret not found |

## Key commands reference

```bash
# Apply a manifest
kubectl apply -f manifests/failures/crash-loop.yaml

# Check pod status
kubectl get pods -n k8s-ai-sre

# Full details + events (most useful for debugging)
kubectl describe pod <pod-name> -n k8s-ai-sre

# View logs
kubectl logs <pod-name> -n k8s-ai-sre

# View logs from previous crashed container
kubectl logs <pod-name> -n k8s-ai-sre --previous

# Delete a pod (clean up between tests)
kubectl delete pod <pod-name> -n k8s-ai-sre

# Delete all failure pods at once
kubectl delete pod crash-loop-pod oom-pod imagepull-pod missing-secret-pod -n k8s-ai-sre
```

## Exit check
Before moving to Phase 2, confirm:
- [ ] `kubectl get nodes` → STATUS: Ready
- [ ] `kubectl get pods -n k8s-ai-sre` shows healthy-nginx Running
- [ ] crash-loop-pod shows CrashLoopBackOff
- [ ] oom-pod shows OOMKilled
- [ ] imagepull-pod shows ImagePullBackOff
- [ ] missing-secret-pod shows Pending

## Decisions log
_Fill this in as you go — what broke, what you changed, what you learned._
