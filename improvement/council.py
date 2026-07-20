"""
Optional "AI council" review: sends pending proposals to multiple frontier models via
OpenRouter for independent opinions, then a judge model synthesizes a consensus recommendation.
This happens BEFORE proposals reach you for approval - it's an extra layer of scrutiny,
not a replacement for your review.

REQUIRES: your own OpenRouter API key (openrouter.ai), set as OPENROUTER_API_KEY.
COSTS MONEY: each run queries multiple models across all pending proposals - real API cost,
billed by OpenRouter to your account. This is entirely optional; if OPENROUTER_API_KEY isn't
set, the analyzer/apply workflow works exactly the same without this step.

This does NOT let the council invent new proposal types or apply anything - it only adds
"council_opinions" and "council_consensus" fields to existing proposals for you to read.

Usage:
    export OPENROUTER_API_KEY="your_key"
    python improvement/council.py
"""

import sys
import os
import json
import urllib.request

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROPOSALS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "improvement_proposals.json")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Pick a small, fixed set of models for cost control. Change these to whatever you want to
# pay for - more models = more API cost per run, no functional benefit beyond diversity of view.
COUNCIL_MODELS = [
    "openai/gpt-5",
    "google/gemini-3-pro",
    "x-ai/grok-4",
]
JUDGE_MODEL = "anthropic/claude-opus-4.6"


def _call_openrouter(model, prompt, max_tokens=400):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }).encode()

    req = urllib.request.Request(
        OPENROUTER_URL, data=body,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
    return result["choices"][0]["message"]["content"]


def _build_prompt(proposal):
    return (
        "You are reviewing a proposed change to an algorithmic trading system's configuration. "
        "The system only allows these change types: demote_to_watchlist, promote_to_active, "
        "adjust_risk_parameter. You cannot suggest anything outside these types.\n\n"
        f"Proposed change: {proposal['type']} for {proposal.get('symbol', '')}\n"
        f"Reason given: {proposal['reason']}\n\n"
        "In under 100 words: do you agree with this specific change? Note any risk of "
        "overfitting to a small sample of walk-forward windows, and whether the evidence "
        "given actually supports this conclusion. End with AGREE, DISAGREE, or UNCERTAIN."
    )


def review_proposal(proposal):
    opinions = {}
    for model in COUNCIL_MODELS:
        try:
            opinions[model] = _call_openrouter(model, _build_prompt(proposal))
        except Exception as e:
            opinions[model] = f"[Error querying {model}: {e}]"

    judge_prompt = (
        "Multiple AI models reviewed this proposed trading system change:\n\n"
        f"Proposal: {proposal['type']} for {proposal.get('symbol', '')}\n"
        f"Reason: {proposal['reason']}\n\n"
        "Opinions:\n" + "\n\n".join(f"{m}: {o}" for m, o in opinions.items()) + "\n\n"
        "Summarize the consensus in 2-3 sentences for a non-expert human who will make the "
        "final approval decision. State clearly whether the models mostly agree, disagree, "
        "or are split, and why."
    )
    try:
        consensus = _call_openrouter(JUDGE_MODEL, judge_prompt, max_tokens=250)
    except Exception as e:
        consensus = f"[Judge model error: {e}]"

    return {"opinions": opinions, "consensus": consensus}


def main():
    if not OPENROUTER_API_KEY:
        print("OPENROUTER_API_KEY not set - skipping AI council review. "
              "This step is optional; proposals still go to human review without it.")
        return

    if not os.path.exists(PROPOSALS_PATH):
        print("No improvement_proposals.json found - nothing to review.")
        return

    with open(PROPOSALS_PATH) as f:
        data = json.load(f)

    reviewed = 0
    for proposal in data.get("proposals", []):
        if proposal.get("applied") or "council_consensus" in proposal:
            continue  # don't re-review already-applied or already-reviewed proposals
        print(f"Council reviewing proposal #{proposal['id']}: {proposal['type']} for {proposal.get('symbol', '')}")
        result = review_proposal(proposal)
        proposal["council_opinions"] = result["opinions"]
        proposal["council_consensus"] = result["consensus"]
        reviewed += 1

    with open(PROPOSALS_PATH, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nCouncil reviewed {reviewed} proposal(s). Consensus notes added for human review.")


if __name__ == "__main__":
    main()
