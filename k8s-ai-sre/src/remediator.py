# remediator.py
# Phase 4 - Final
# Only file with write access to Kubernetes.
# Only auto-executes LOW risk actions.

from kubernetes import client, config
from datetime import datetime

NAMESPACE = "k8s-ai-sre"

action_log = []

def log_action(pod_name, action, result):
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pod":       pod_name,
        "action":    action,
        "result":    result,
    }
    action_log.append(entry)
    print(f"\n📋 ACTION LOG: [{entry['timestamp']}] {action} on {pod_name} → {result}")

def get_pod_owner_kind(pod_name):
    config.load_kube_config()
    v1 = client.CoreV1Api()
    try:
        pod    = v1.read_namespaced_pod(name=pod_name, namespace=NAMESPACE)
        owners = pod.metadata.owner_references
        if owners:
            return owners[0].kind
        return None
    except Exception as e:
        print(f"[!] Could not check pod owner: {e}")
        return None

def restart_pod(pod_name):
    owner_kind = get_pod_owner_kind(pod_name)

    if owner_kind == "ReplicaSet":
        try:
            config.load_kube_config()
            v1 = client.CoreV1Api()
            v1.delete_namespaced_pod(name=pod_name, namespace=NAMESPACE)
            log_action(pod_name, "delete_pod (Deployment will recreate)", "success")
            return True, "Pod deleted — Deployment is recreating it"
        except Exception as e:
            log_action(pod_name, "delete_pod", f"failed: {e}")
            return False, f"Failed to delete pod: {e}"

    elif owner_kind in ("DaemonSet", "StatefulSet"):
        log_action(pod_name, "restart_skipped", f"owned by {owner_kind} — needs manual review")
        return False, f"Pod owned by {owner_kind} — skipping auto-restart, manual review needed"

    else:
        log_action(pod_name, "restart_skipped", "bare pod — no controller to recreate it")
        return False, "Bare pod detected — auto-restart skipped to avoid permanent deletion"

def remediate(pod_name, diagnosis):
    error_type = diagnosis.get("error_type", "Other")
    risk_level = diagnosis.get("risk_level", "high")

    print(f"\n🔧 REMEDIATOR: {pod_name} | error={error_type} | risk={risk_level}")

    if risk_level != "low":
        log_action(pod_name, "remediation_skipped", f"risk={risk_level} — human review needed")
        return False, f"Risk level is {risk_level} — skipping auto-remediation"

    if error_type == "CrashLoopBackOff":
        return restart_pod(pod_name)

    elif error_type == "OOMKilled":
        log_action(pod_name, "oom_restart_skipped",
                   "OOMKilled needs memory limit increase — cannot auto-fix safely")
        return False, "OOMKilled requires memory limit change — flagged for human review"

    elif error_type == "ImagePullBackOff":
        log_action(pod_name, "imagepull_skipped",
                   "Image pull failure needs image name or credential fix — cannot auto-fix")
        return False, "ImagePullBackOff requires image or credential fix — flagged for human"

    elif error_type == "MissingSecret":
        log_action(pod_name, "secret_skipped",
                   "Missing secret needs manual creation — cannot auto-fix")
        return False, "Missing secret requires manual creation — flagged for human"

    else:
        # Claude returned "Other" — attempt generic restart as fallback
        print(f"   error_type=Other — attempting generic pod restart")
        return restart_pod(pod_name)
