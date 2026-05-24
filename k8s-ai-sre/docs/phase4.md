# Phase 4 — Auto-Remediation & Alerting

## Goal
When a pod fails, Claude diagnoses it and either auto-remediates (low risk)
or sends a detailed email alert (medium/high risk) — with zero manual intervention
for detection and diagnosis.

## What was built

| File | Job |
|---|---|
| `src/remediator.py` | Executes fix actions on the cluster — only file with write access |
| `src/notifier.py` | Sends HTML email via Gmail SMTP with full fix plan |
| `src/watcher.py` | Updated — risk gate + incident-based deduplication |

## Architecture — full Phase 4 pipeline

```
Pod enters bad state (ANY error)
        │
        ▼
watcher.py — get_incident_key() maps pod → Deployment name
        │     get_bad_state() detects any non-zero exit or bad waiting reason
        │     incidents{} checks — new incident? suppressed? recovered?
        │
        ▼
collector.py — fetches logs, events, pod summary
        │
        ▼
claude_agent.py — sends evidence + web_search tool to Claude API
        │          Claude searches for the specific error
        │          returns structured JSON: cause, steps, risk, sources
        │
        ▼
        ├── risk_level: low  → remediator.py → attempt auto-fix
        │                    → notifier.py   → email with fix result
        │
        └── risk_level: medium/high → notifier.py → email for human review
```

## Key design decisions

### Incident-based deduplication
**Problem:** Kubernetes sends a stream of MODIFIED events constantly. A pod
oscillating between CrashLoopBackOff and Terminated:exit1 would trigger
dozens of emails without deduplication.

**Solution:** Track incidents by Deployment name (not pod name) with three states:
- ALERTED — email sent, suppress all further events for this incident
- RESOLVED — pod recovered, incident closed, ready for next crash
- New crash after RESOLVED → genuine new incident → alert again

**Why Deployment name, not pod name:**
When a Deployment recreates a pod after deletion, the pod gets a new suffix.
Tracking by pod name would open a new incident for each recreation.
Stripping the ReplicaSet hash gives a stable key across pod recreations.

### Catch-all error detection
**Before:** Only detected 4 hardcoded error types.
**After:** Detects any pod failure:
- Any waiting reason except ContainerCreating and PodInitializing
- Any non-zero exit code
- OOMKilled by name
- Unschedulable pods

Claude handles diagnosis for all of them via web search — no new code needed
when a new error type appears in the cluster.

### Risk gate logic
- LOW    → auto-remediate + email with result
- MEDIUM → email only, human decides
- HIGH   → email only, human decides

Claude sets the risk level based on what it finds while searching.

### Remediator — write access boundary
Only remediator.py calls write APIs on Kubernetes. All other files are
read-only. This contains the blast radius — a bug in the watcher or agent
can never accidentally delete or modify cluster resources.

**Auto-fix actions by error type:**

| Error type | Action | Why |
|---|---|---|
| CrashLoopBackOff | Delete pod (Deployment-managed only) | Deployment recreates cleanly |
| OOMKilled | Skip — email only | Need correct memory value first |
| ImagePullBackOff | Skip — email only | Need image name or credentials |
| MissingSecret | Skip — email only | Need to know secret values |
| Other | Attempt generic restart | Claude could not classify — try restart |
| Bare pod | Skip — email only | Deletion is permanent, no controller |

## Email alert content
Every alert contains: pod name, risk level (colour coded), root cause,
numbered fix steps with exact kubectl commands, web searches Claude ran,
sources Claude read with links, and auto-remediation result if attempted.

## Mini-milestones completed

### M4.1 — remediator.py
- Checks pod owner before any deletion
- Deployment-managed pods safe to delete — controller recreates
- Bare pods never auto-deleted
- All actions written to in-memory audit log

### M4.2 — Risk gate
- Claude's risk_level field drives the decision
- Low → attempt fix then email result
- Medium/High → email immediately, no cluster changes

### M4.3 — Gmail alerts
- HTML formatted email with full fix plan
- Plain text fallback for all email clients
- Python built-in smtplib — no extra library needed

## Exit check
- [x] Any pod failure detected — not just 4 hardcoded types
- [x] One email per incident regardless of state oscillation
- [x] Pod recovery closes incident automatically
- [x] Same pod crashes again after recovery — new incident fires
- [x] Deployment pods tracked by Deployment name across recreations

## Decisions log
- Incident key = Deployment name not pod name. Pod name changes on every
  recreation. Deployment name is stable across the lifetime of the workload.
- Exit code normalisation: common crash codes map to CrashLoopBackOff
  so remediator can match them consistently.
- OOMKilled intentionally skipped in remediator — increasing memory limits
  without knowing the right value could mask underlying memory leaks.
- Gmail App Password used — required by Google for SMTP, more secure than
  main password, can be revoked independently without changing Gmail login.
