# k8s-ai-sre
### Autonomous Kubernetes remediation agent powered by Claude AI

An AI agent that watches your Kubernetes cluster, detects any pod failure,
searches the web to diagnose the error exactly like a human SRE would,
and either auto-remediates or emails you a complete fix plan instantly.

---

## How it works

```
Pod fails (any error)
    │
    ▼
Watcher detects bad state
    │
    ▼
Collector fetches logs + events + pod state
    │
    ▼
Claude receives evidence + searches the web for the error
    │
    ▼
Structured diagnosis: root cause · fix steps · risk level · sources
    │
    ├── Low risk  → auto-remediate + email result
    └── Med/High  → email fix plan for human review
```

## Features

- **Detects any failure** — CrashLoopBackOff, OOMKilled, ImagePullBackOff,
  missing secrets, unknown exit codes, custom app errors
- **AI-powered diagnosis** — Claude searches the web for the specific error,
  reads docs and GitHub issues, returns actionable fix steps with sources
- **Incident deduplication** — one alert per incident, not per Kubernetes event
- **Safe auto-remediation** — only acts on low-risk fixes, never guesses
- **Email alerts** — HTML formatted with full fix plan delivered instantly
- **Zero hardcoded rules** — Claude handles new error types automatically

## Stack

| Component | Tool | Cost |
|---|---|---|
| Kubernetes | Minikube (local) | Free |
| AI / LLM | Claude API (Anthropic) | Free credits on signup |
| Web search | Claude built-in web_search tool | Included in API |
| Notifications | Gmail SMTP | Free |
| Language | Python 3.12+ | Free |

## Project structure

```
k8s-ai-sre/
├── src/
│   ├── collector.py      # fetches logs, events, pod state from cluster
│   ├── watcher.py        # watches namespace, manages incidents
│   ├── claude_agent.py   # sends evidence to Claude, gets diagnosis
│   ├── remediator.py     # executes fix actions (only write-access file)
│   └── notifier.py       # sends Gmail alerts
├── manifests/
│   ├── healthy/
│   │   └── healthy-pod.yaml
│   └── failures/
│       ├── crash-loop.yaml
│       ├── oom-killed.yaml
│       ├── image-pull-error.yaml
│       └── missing-secret.yaml
├── docs/
│   ├── phase1.md         # cluster setup
│   ├── phase2.md         # Claude reads cluster
│   ├── phase3.md         # web search + diagnosis
│   └── phase4.md         # auto-remediation + alerts
├── .env.example
├── .gitignore
└── README.md
```

## Setup

### Prerequisites
- Windows 11 / macOS / Linux
- Docker Desktop
- Minikube
- Python 3.12+
- Claude API key (console.anthropic.com)
- Gmail account with App Password enabled

### Install

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/k8s-ai-sre.git
cd k8s-ai-sre

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

# Install dependencies
pip install kubernetes anthropic python-dotenv

# Copy env template and fill in your keys
copy .env.example .env      # Windows
cp .env.example .env        # macOS/Linux
```

### Configure `.env`

```
ANTHROPIC_API_KEY=sk-ant-...
GMAIL_SENDER=your@gmail.com
GMAIL_APP_PASSWORD=your-16-char-app-password
GMAIL_RECEIVER=your@gmail.com
```

### Start your cluster

```bash
minikube start --driver=docker
kubectl create namespace k8s-ai-sre
```

### Run the agent

```bash
python src/watcher.py
```

### Simulate failures (for testing)

```bash
kubectl apply -f manifests/failures/crash-loop.yaml
kubectl apply -f manifests/failures/oom-killed.yaml
kubectl apply -f manifests/failures/image-pull-error.yaml
kubectl apply -f manifests/failures/missing-secret.yaml
```

## Phases

| Phase | Description | Status |
|---|---|---|
| 1 | Kubernetes cluster setup + failure simulations | ✅ Complete |
| 2 | Claude reads cluster — watcher + log fetcher | ✅ Complete |
| 3 | Claude searches web + structured fix plans | ✅ Complete |
| 4 | Auto-remediation + Gmail alerts | ✅ Complete |
| 5 | Audit log + documentation site | 🔄 In progress |

## License
MIT
