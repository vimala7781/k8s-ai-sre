# claude_agent.py
# Phase 2 - M2.4 / Phase 3 - M3.1 + M3.2
# Job: receive evidence bundle from the watcher,
# send it to Claude with web_search enabled,
# and return a structured diagnosis + fix plan.
#
# Claude behaves like a senior SRE here:
# - reads the evidence
# - searches the web for the error
# - reads what it finds
# - returns a fix plan with sources cited

import os
import json
import anthropic
from dotenv import load_dotenv

# Load ANTHROPIC_API_KEY from .env file
load_dotenv()

# ── Build the prompt ─────────────────────────────────────────────
# This is the most important function in the project.
# The prompt is what shapes how Claude thinks about the problem.
# We give it:
#   1. A role — senior SRE who searches before answering
#   2. The raw evidence — summary, logs, events
#   3. A strict output format — so we can parse the response in code
#
# We ask for JSON output so the watcher can read it programmatically
# rather than parsing free-form text.

def build_prompt(evidence: dict) -> str:
    return f"""You are a senior Kubernetes SRE (Site Reliability Engineer).
A pod in the cluster has entered a bad state. Your job is to:
1. Analyse the evidence below
2. Search the web for the specific error to find known fixes
3. Return a structured diagnosis

EVIDENCE:
---------
Pod: {evidence['pod_name']}
Namespace: {evidence['namespace']}

SUMMARY:
{evidence['summary']}

LOGS:
{evidence['logs']}

EVENTS:
{evidence['events']}

---------
INSTRUCTIONS:
- Use the web_search tool to search for the specific error you see
- Search at least once, more if needed to find a good fix
- After searching, return ONLY a JSON object in this exact format:

{{
  "root_cause": "one clear sentence explaining why the pod failed",
  "confidence": "high | medium | low",
  "error_type": "CrashLoopBackOff | OOMKilled | ImagePullBackOff | MissingSecret | Other",
  "fix_steps": [
    "Step 1 — specific action to take",
    "Step 2 — next action",
    "Step 3 — verification step"
  ],
  "risk_level": "low | medium | high",
  "risk_reason": "why this fix is that risk level",
  "sources": [
    "url or description of source that informed this fix"
  ],
  "search_queries_used": [
    "the actual queries you searched"
  ]
}}

Return ONLY the JSON. No preamble, no explanation outside the JSON."""


# ── Call Claude with web search ──────────────────────────────────
# We use the tool_use feature of the Anthropic API.
# web_search_20250305 is Claude's built-in search tool —
# no external API key needed, it's included in the API.
#
# Claude may call the tool multiple times before returning the JSON.
# We keep processing until Claude gives us a final text response
# (that's when it's done searching and ready to answer).

def diagnose(evidence: dict) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in .env file")

    claude = anthropic.Anthropic(api_key=api_key)

    print(f"\n🤖 Sending evidence to Claude...")
    print(f"   Pod: {evidence['pod_name']}")

    messages = [
        {"role": "user", "content": build_prompt(evidence)}
    ]

    # Keep looping until Claude returns a final text response
    # Each iteration may be Claude using the search tool
    search_count = 0

    while True:
        response = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            tools=[
                {
                    "type": "web_search_20250305",
                    "name": "web_search"
                }
            ],
            messages=messages
        )

        # Check what Claude returned
        if response.stop_reason == "end_turn":
            # Claude is done — extract the final text response
            for block in response.content:
                if hasattr(block, "text"):
                    return parse_diagnosis(block.text, evidence["pod_name"])
            break

        elif response.stop_reason == "tool_use":
            # Claude wants to search — let the API handle it
            # We need to add Claude's response to messages and continue
            search_count += 1
            print(f"   🔍 Claude is searching... (search #{search_count})")

            # Add Claude's tool use message to conversation history
            messages.append({
                "role": "assistant",
                "content": response.content
            })

            # Process tool results and add them back
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    # For web_search, the results come back automatically
                    # We just need to acknowledge the tool call
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Search completed"
                    })

            if tool_results:
                messages.append({
                    "role": "user",
                    "content": tool_results
                })
        else:
            # Unexpected stop reason
            break

    return {
        "pod_name": evidence["pod_name"],
        "error": "Claude did not return a diagnosis",
        "raw_response": str(response)
    }


# ── Parse Claude's JSON response ─────────────────────────────────
# Claude should return clean JSON but sometimes adds a small
# preamble or wraps it in markdown code fences.
# This function handles both cases safely.

def parse_diagnosis(text: str, pod_name: str) -> dict:
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        text = "\n".join(lines[1:-1])

    try:
        diagnosis = json.loads(text)
        diagnosis["pod_name"] = pod_name
        return diagnosis
    except json.JSONDecodeError:
        # Claude didn't return valid JSON — return raw text
        return {
            "pod_name": pod_name,
            "root_cause": "Could not parse Claude response",
            "raw_response": text
        }


# ── Pretty print the diagnosis ───────────────────────────────────
# Called by the watcher to display the result clearly.

def print_diagnosis(diagnosis: dict):
    print(f"\n{'='*60}")
    print(f"🔍 CLAUDE DIAGNOSIS: {diagnosis.get('pod_name', 'unknown')}")
    print(f"{'='*60}")

    if "raw_response" in diagnosis:
        print(f"Raw response:\n{diagnosis['raw_response']}")
        return

    print(f"\n📌 Root cause:  {diagnosis.get('root_cause', 'N/A')}")
    print(f"📊 Confidence:  {diagnosis.get('confidence', 'N/A')}")
    print(f"⚠️  Risk level:  {diagnosis.get('risk_level', 'N/A')}")
    print(f"💬 Risk reason: {diagnosis.get('risk_reason', 'N/A')}")

    print(f"\n🔧 Fix steps:")
    for i, step in enumerate(diagnosis.get("fix_steps", []), 1):
        print(f"   {i}. {step}")

    print(f"\n🔎 Searches used:")
    for q in diagnosis.get("search_queries_used", []):
        print(f"   • {q}")

    print(f"\n📚 Sources:")
    for s in diagnosis.get("sources", []):
        print(f"   • {s}")

    print(f"{'='*60}\n")


# ── Test — run this file directly to test on one pod ─────────────
# This lets you test the agent without running the full watcher.
# Hardcoded to test crash-loop-pod — change pod_name to test others.

if __name__ == "__main__":
    from collector import connect_to_cluster, collect_pod_evidence

    connect_to_cluster()

    # Change this to test different pods:
    # "crash-loop-pod", "imagepull-pod", "missing-secret-pod", "oom-pod"
    pod_name = "crash-loop-pod"

    print(f"Collecting evidence for: {pod_name}")
    evidence = collect_pod_evidence(pod_name)

    print(f"Sending to Claude with web search...")
    diagnosis = diagnose(evidence)

    print_diagnosis(diagnosis)
