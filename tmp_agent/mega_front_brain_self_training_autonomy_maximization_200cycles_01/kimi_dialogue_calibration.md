# Kimi Open Autonomy Dialogue Calibration

- stable_count: `6/8`
- stability_ratio: `0.75`
- status: `KIMI_OPEN_AUTONOMY_DIALOGUE_STABLE`
- recommended_mode: `use_kimi_for_constrained_open_dialogue`

| profile | provider | status | fallback | non_empty | no_cot | stable |
|---|---|---|---:|---:|---:|---:|
| exact_output | kimi_k2_6_cloud | FAST_SUCCESS | False | True | True | True |
| bullet_only | kimi_k2_6_cloud | FAST_SUCCESS | False | True | True | True |
| json_only | kimi_k2_6_cloud | FAST_SUCCESS | False | True | True | True |
| role_compressed | kimi_k2_6_cloud | FAST_SUCCESS | False | True | True | True |
| one_sentence_proposal | kimi_k2_6_cloud | FAST_SUCCESS | False | True | True | True |
| critic | kimi_k2_6_cloud | FAST_SUCCESS | False | True | True | True |
| revise | codex | FAST_SUCCESS | True | True | True | False |
| score | codex | FAST_SUCCESS | True | True | True | False |
