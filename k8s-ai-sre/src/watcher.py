# watcher.py
# Phase 4 - Final
# Detects ANY pod failure — not just the 4 hardcoded types
# incident-based deduplication — tracks by Deployment name, not pod name

import time
from datetime import datetime
from kubernetes import client, config, watch

from collector    import collect_pod_evidence, connect_to_cluster
from claude_agent import diagnose, print_diagnosis
from remediator   import remediate
from notifier     import send_alert

NAMESPACE = "k8s-ai-sre"

# Waiting reasons that mean "still starting up" — not failures
HEALTHY_WAITING_REASONS = {
    "ContainerCreating",
    "PodInitializing",
    "Pending",
}

# ── Incident tracker ─────────────────────────────────────────────
incidents = {}

# ── Get stable incident key ──────────────────────────────────────
def get_incident_key(pod):
    owners = pod.metadata.owner_references
    if owners:
        owner = owners[0]
        if owner.kind == "ReplicaSet":
            rs_name = owner.name
            parts   = rs_name.rsplit("-", 1)
            return parts[0] if len(parts) == 2 else rs_name
        return owner.name
    return pod.metadata.name

# ── Determine if a pod needs diagnosis ──────────────────────────
# Catches ANY failure — not just hardcoded types
# This means custom app errors, unknown exit codes, new k8s states
# all get diagnosed by Claude automatically

def get_bad_state(pod):
    if not pod.status.container_statuses:
        # No container status yet — check for scheduling failures
        if pod.status.phase == "Pending":
            if pod.status.conditions:
                for condition in pod.status.conditions:
                    if condition.reason == "Unschedulable":
                        return f"Pending:Unschedulable"
        return None

    for cs in pod.status.container_statuses:

        # ── Waiting states ───────────────────────────────────────
        if cs.state.waiting:
            reason = cs.state.waiting.reason
            if not reason:
                continue

            # Skip healthy transient states
            if reason in HEALTHY_WAITING_REASONS:
                continue

            # Normalise image pull variants
            if reason in ("ErrImagePull", "ImagePullBackOff"):
                return "ImagePullBackOff"

            # Everything else waiting = bad (CrashLoopBackOff,
            # CreateContainerConfigError, InvalidImageName, etc.)
            return reason

        # ── Terminated states ────────────────────────────────────
        if cs.state.terminated:
            exit_code = cs.state.terminated.exit_code
            reason    = cs.state.terminated.reason

            # OOMKilled is a named reason — use it directly
            if reason == "OOMKilled":
                return "OOMKilled"

            # Exit code 0 = clean exit (Job completed etc.) — not a failure
            if exit_code == 0:
                continue

            # ANY non-zero exit code = failure worth diagnosing
            # Normalise crash-loop related codes to CrashLoopBackOff
            # so remediator can match them
            if exit_code in (1, 2, 126, 127, 128, 130, 134, 139, 143):
                return "CrashLoopBackOff"

            # Unknown exit code — still diagnose it, Claude will search it
            return f"Terminated:exit{exit_code}"

    return None

# ── Handle a bad pod — full pipeline ────────────────────────────

def handle_bad_pod(pod_name, incident_key, bad_state):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n{'='*60}")
    print(f"[{timestamp}] 🚨 NEW INCIDENT: {incident_key} (pod: {pod_name})")
    print(f"State: {bad_state}")
    print(f"{'='*60}")

    evidence  = collect_pod_evidence(pod_name)
    diagnosis = diagnose(evidence)
    print_diagnosis(diagnosis)

    risk_level = diagnosis.get("risk_level", "high")

    if risk_level == "low":
        print(f"\n✅ Risk is LOW — attempting auto-remediation...")
        success, result_msg = remediate(pod_name, diagnosis)
        if success:
            print(f"✅ Auto-remediation succeeded: {result_msg}")
        else:
            print(f"⚠️  Auto-remediation skipped: {result_msg}")
        send_alert(pod_name, diagnosis, remediation_result=result_msg)
    else:
        print(f"\n🚨 Risk is {risk_level.upper()} — alerting human, no auto-fix...")
        send_alert(pod_name, diagnosis, remediation_result=None)

    print(f"\n[{timestamp}] Pipeline complete for {incident_key}")
    print(f"{'='*60}\n")

# ── Main watch loop ──────────────────────────────────────────────

def run_watcher():
    connect_to_cluster()
    v1 = client.CoreV1Api()
    w  = watch.Watch()

    print(f"\n👀 Watching namespace: {NAMESPACE}")
    print(f"Detects ANY pod failure — Claude searches for the fix")
    print(f"Incident-based deduplication — one alert per incident")
    print(f"Waiting for bad pods... (Ctrl+C to stop)\n")

    while True:
        try:
            for event in w.stream(
                v1.list_namespaced_pod,
                namespace=NAMESPACE,
                timeout_seconds=300
            ):
                event_type   = event["type"]
                pod          = event["object"]
                pod_name     = pod.metadata.name
                incident_key = get_incident_key(pod)

                if event_type == "DELETED":
                    owners = pod.metadata.owner_references
                    if not owners and incident_key in incidents:
                        print(f"🗑️  [{incident_key}] bare pod deleted — clearing incident")
                        del incidents[incident_key]
                    continue

                bad_state = get_bad_state(pod)

                if bad_state:
                    existing = incidents.get(incident_key)

                    if not existing:
                        print(f"🆕 New incident opened: {incident_key} ({bad_state})")
                        incidents[incident_key] = {
                            "state":     "ALERTED",
                            "bad_state": bad_state,
                            "pod_name":  pod_name,
                            "time":      datetime.now().timestamp()
                        }
                        handle_bad_pod(pod_name, incident_key, bad_state)

                    elif existing["state"] == "ALERTED":
                        print(f"🔕 [{incident_key}] incident active — suppressing duplicate ({bad_state})")

                    elif existing["state"] == "RESOLVED":
                        print(f"🔁 [{incident_key}] crashed again after recovery — new incident")
                        incidents[incident_key] = {
                            "state":     "ALERTED",
                            "bad_state": bad_state,
                            "pod_name":  pod_name,
                            "time":      datetime.now().timestamp()
                        }
                        handle_bad_pod(pod_name, incident_key, bad_state)

                else:
                    if incident_key in incidents:
                        existing = incidents[incident_key]
                        if existing["state"] == "ALERTED":
                            print(f"✅ [{incident_key}] recovered — incident resolved automatically")
                        incidents[incident_key]["state"] = "RESOLVED"
                        del incidents[incident_key]

        except KeyboardInterrupt:
            print("\n\nWatcher stopped.")
            print(f"Active incidents at shutdown: {list(incidents.keys()) or 'none'}")
            break
        except Exception as e:
            print(f"\n[!] Watcher error: {e}")
            print(f"    Reconnecting in 5 seconds...")
            time.sleep(5)
            continue

if __name__ == "__main__":
    run_watcher()
