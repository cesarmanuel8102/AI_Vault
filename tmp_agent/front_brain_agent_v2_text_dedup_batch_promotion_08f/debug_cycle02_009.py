import json
import sys
from pathlib import Path

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from tmp_agent.brain_v9.memory.promotion_pipeline_adapter import PromotionPipelineAdapter

adapter = PromotionPipelineAdapter()
cands = adapter.load_candidates("all")
for c in cands:
    if c["candidate_id"] == "cycle02_retry_candidate_009":
        print("source_bucket:", c.get("source_bucket"))
        print("source_cycle:", c.get("source_cycle"))
        print("domain:", c.get("domain"))
        print("domain_review_required:", c.get("domain_review_required"))
        print("text:", repr(c.get("text", "")[:80]))
        print("validation:", adapter.validate_candidate(c))
        break
