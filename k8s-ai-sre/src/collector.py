# collector.py
# Phase 2 - M2.2
# Job: connect to the Kubernetes cluster and collect everything
# about a pod that Claude will need to diagnose it.
#
# Think of this as the "kubectl logs + describe" step,
# but done from Python so our agent can call it automatically.

from kubernetes import client, config

# ── Connect to cluster ──────────────────────────────────────────
# This reads ~/.kube/config — the same file minikube wrote when
# you ran `minikube start`. It tells Python where the cluster is
# and how to authenticate with it. Same as how kubectl knows
# where to connect.

def connect_to_cluster():
    config.load_kube_config()
    print("✓ Connected to cluster")

# ── Get all pods in our namespace ───────────────────────────────
# CoreV1Api is the Kubernetes API group that handles pods,
# namespaces, secrets, configmaps — the core resources.
# Think of it as the "department" inside Kubernetes we call.

NAMESPACE = "k8s-ai-sre"

def list_pods():
    v1 = client.CoreV1Api()
    pods = v1.list_namespaced_pod(namespace=NAMESPACE)

    print(f"\n── Pods in {NAMESPACE} ──")
    for pod in pods.items:
        name   = pod.metadata.name
        status = pod.status.phase          # Running, Pending, Failed
        
        # Container status is nested one level deeper
        # A pod can have multiple containers — we check the first one
        container_statuses = pod.status.container_statuses
        if container_statuses:
            state = container_statuses[0].state
            if state.waiting:
                # Waiting = CrashLoopBackOff, ImagePullBackOff, etc.
                display = f"Waiting: {state.waiting.reason}"
            elif state.running:
                display = "Running"
            elif state.terminated:
                display = f"Terminated: exit code {state.terminated.exit_code}"
            else:
                display = "Unknown"
        else:
            display = f"Phase: {status}"   # Pending pods have no container status yet

        print(f"  {name:<45} {display}")

    return pods.items

# ── Fetch logs for a pod ────────────────────────────────────────
# This is equivalent to: kubectl logs <pod> -n k8s-ai-sre
# We fetch the last 50 lines — enough context without flooding Claude.
# For crashloop pods the last 50 lines contain the error.

def get_logs(pod_name):
    v1 = client.CoreV1Api()
    try:
        logs = v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=NAMESPACE,
            tail_lines=50,          # last 50 lines only
            previous=False          # set True to get logs from crashed container
        )
        return logs if logs.strip() else "(no logs — container may not have started)"
    except Exception as e:
        return f"(could not fetch logs: {e})"

# ── Fetch events for a pod ──────────────────────────────────────
# Events are what `kubectl describe pod` shows at the bottom.
# This is where ImagePullBackOff, secret not found, OOMKilled live.
# For most failure types, events tell more than logs do.

def get_events(pod_name):
    v1 = client.CoreV1Api()
    # Events are stored cluster-wide and filtered by pod name
    # field_selector is like a WHERE clause — give me events for this pod only
    events = v1.list_namespaced_event(
        namespace=NAMESPACE,
        field_selector=f"involvedObject.name={pod_name}"
    )

    if not events.items:
        return "(no events found)"

    lines = []
    for event in events.items:
        # type is Normal or Warning — we care most about Warning
        lines.append(f"  [{event.type}] {event.reason}: {event.message}")

    return "\n".join(lines)

# ── Fetch describe-style summary ────────────────────────────────
# Pulls together the key fields from the pod object itself —
# restart count, exit code, reason — the things Claude needs
# to identify what kind of failure this is.

def get_pod_summary(pod_name):
    v1 = client.CoreV1Api()
    try:
        pod = v1.read_namespaced_pod(name=pod_name, namespace=NAMESPACE)
    except Exception as e:
        return f"(could not read pod: {e})"

    lines = []
    lines.append(f"Pod: {pod.metadata.name}")
    lines.append(f"Namespace: {pod.metadata.namespace}")
    lines.append(f"Phase: {pod.status.phase}")

    # Container state details
    if pod.status.container_statuses:
        for cs in pod.status.container_statuses:
            lines.append(f"Container: {cs.name}")
            lines.append(f"  Image: {cs.image}")
            lines.append(f"  Restart count: {cs.restart_count}")
            lines.append(f"  Ready: {cs.ready}")

            # Current state
            if cs.state.waiting:
                lines.append(f"  State: Waiting — {cs.state.waiting.reason}")
                if cs.state.waiting.message:
                    lines.append(f"  Message: {cs.state.waiting.message}")

            elif cs.state.terminated:
                lines.append(f"  State: Terminated")
                lines.append(f"  Exit code: {cs.state.terminated.exit_code}")
                lines.append(f"  Reason: {cs.state.terminated.reason}")

            # Last state — what happened in the previous run (crucial for crashloop)
            if cs.last_state.terminated:
                lines.append(f"  Last exit code: {cs.last_state.terminated.exit_code}")
                lines.append(f"  Last reason: {cs.last_state.terminated.reason}")

    return "\n".join(lines)

# ── Bundle everything into one package for Claude ───────────────
# This is the function the agent will call in Phase 3.
# It returns a single dictionary with all the evidence.

def collect_pod_evidence(pod_name):
    print(f"\n── Collecting evidence for: {pod_name} ──")

    evidence = {
        "pod_name":   pod_name,
        "namespace":  NAMESPACE,
        "summary":    get_pod_summary(pod_name),
        "logs":       get_logs(pod_name),
        "events":     get_events(pod_name),
    }

    print(f"  summary:  {len(evidence['summary'])} chars")
    print(f"  logs:     {len(evidence['logs'])} chars")
    print(f"  events:   {len(evidence['events'])} chars")

    return evidence

# ── Main — run this file directly to test ───────────────────────
# When you run `python src/collector.py` this block executes.
# It lists all pods, then collects full evidence for each bad one.
# In Phase 3 the watcher will call collect_pod_evidence() directly
# instead of running this file.

if __name__ == "__main__":
    connect_to_cluster()
    pods = list_pods()

    # Collect evidence for pods that are NOT running normally
    bad_states = {"Failed", "Pending"}
    print("\n── Collecting evidence for unhealthy pods ──")

    for pod in pods:
        phase = pod.status.phase
        name  = pod.metadata.name

        # Check container-level states too — CrashLoopBackOff shows phase=Running
        is_bad = False
        if phase in bad_states:
            is_bad = True
        if pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                if cs.state.waiting and cs.state.waiting.reason in (
                    "CrashLoopBackOff", "ImagePullBackOff",
                    "ErrImagePull", "CreateContainerConfigError"
                ):
                    is_bad = True
                if cs.state.terminated and cs.state.terminated.exit_code != 0:
                    is_bad = True

        if is_bad:
            evidence = collect_pod_evidence(name)
            print(f"\n{'='*50}")
            print(f"SUMMARY:\n{evidence['summary']}")
            print(f"\nLOGS:\n{evidence['logs']}")
            print(f"\nEVENTS:\n{evidence['events']}")
            print(f"{'='*50}")
