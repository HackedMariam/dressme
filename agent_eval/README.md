# agent_eval: LLM judge for every DressMe agent

An LLM scores each agent's answer from 1 to 5 on a small rubric (`rubrics.py`), using only the facts the agent had.
A case passes when the average reaches 3.5 **and** every `hard` criterion (grounding, no invented garment, decision follows
the evidence...) is at least 3.

Agents: stylist, outfit, wardrobe, similar, orchestrator, trip, gap, purchase, rag.

```bash
python -m agent_eval.run_eval                     # recorded cases (cases/<agent>.jsonl with an "output")
python -m agent_eval.run_eval stylist trip        # some agents only
python -m agent_eval.run_eval --live --token JWT  # call the running agents over A2A (stylist, outfit, wardrobe, similar, trip, gap)
python -m agent_eval.run_eval --min-pass 0.8      # exit 1 below 80 % passing (CI gate)
python -m pytest agent_eval/tests                 # offline tests of the judge (fake LLM, no key needed)
```

Judge model: `JUDGE_MODEL` (else `LLM_MODEL`), endpoint `LLM_BASE_URL`, key `OPENAI_API_KEY`: same `.env` as the rest.
Use a different (ideally stronger) model than the agents' own to limit self-preference bias.

Case line: `{"id", "input", "data"?, "context"?, "output"?}`. `context` = the facts the agent had (wardrobe, weather, tool
evidence, retrieved passages): without it the judge cannot detect hallucinations. Without `output`, `--live` fills both.
Each agent has a good case and a deliberately bad one (invented garment, wrong route...): the judge must pass the first and
fail the second; if it does not, fix the rubric before trusting any score. Results go to `results/<timestamp>.json`.
