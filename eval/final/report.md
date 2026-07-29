# RAG Evaluation Report

## Configuration

- Result contract: v2
- Run: `20260729T074749Z`; created `2026-07-29T07:47:49.775213+00:00`
- Dataset: `eval/data/ground_truth.json`; SHA-256 `74fc10f6fbc982eb52abf18e76d41ab538a69b967d70cd7f04c1d6559e86191f`; version `2`; review status `draft`; 250 result rows
- Corpus manifest: `eval/data/corpus_manifest.json`; SHA-256 `aa50b24181d8d8701bcb1ead2b6e678893845a3d7587ceb9977f4a7535f53789`; version `2`; documents `1`; indexed chunks `209`
- Corpus document: `docs/samples/NIST.CSWP.29_CSF-2.0.pdf`; SHA-256 `3c31f46fee98cac0c4323453e5109291a213b4de7fef8c058af9bf67f717433c`; pages `32`; indexed chunks `209`
- Candidate models: `["llama3.2:latest","qwen2.5:1.5b","gemma2:2b","phi4-mini:latest","gemma4:e2b"]`; digests `{"gemma2:2b":"8ccf136fdd5298f3ffe2d69862750ea7fb56555fa4d5b18c04e3fa4d82ee09d7","gemma4:e2b":"7fbdbf8f5e45a75bb122155ed546e765b4d9c53a1285f62fd9f506baa1c5a47e","llama3.2:latest":"a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72","phi4-mini:latest":"78fad5d182a7c33065e153a5f8ba210754207ba9d91973f57dffa7f487363753","qwen2.5:1.5b":"65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b"}`
- Embedding model: `nomic-embed-text:latest`; digest `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`
- Generation settings: `{"num_ctx":8192,"num_predict":512,"seed":42,"stop":[],"temperature":0,"think":false}`
- Retrieval settings: `{"generator_context_limit":5,"mode":"hybrid","rerank_enabled":false,"retrieval_limit":10,"rrf_k":60,"top_k_bm25":20,"top_k_dense":20}`
- Question limit: `all`; metrics `["cosine_similarity","bertscore","llm_judge"]`
- Cosine similarity: threshold `0.75`
- BERTScore: threshold `0.85`, raw precision/recall/F1
- BERTScore scorer: `FacebookAI/roberta-large`, revision `722cf37b1afa9454edce342e7895e588b6ff1d59`, layer `17`, device `cpu`, IDF `False`, baseline rescaling `False`, scorer hash `FacebookAI/roberta-large_L17_no-idf_version=0.3.12(hug_trans=5.8.1)`, package `bert-score` `0.3.13`
- LLM judge: enabled `True`; provider `groq`; model `openai/gpt-oss-120b`; temperature `0`; request policy `{"max_retry_delay_seconds":60.0,"max_total_attempts":5,"sdk_max_retries":0}`; cache bypassed `True`
- Judge execution continuity: judgments were completed across multiple user-authorized Groq credentials and quota windows. Provider, model, temperature, prompt, request policy, rubric, and no-cache settings remained fixed. Credential and organization identifiers are not retained, and no account or service-tier equivalence is claimed.

Cosine similarity, BERTScore, and the LLM judge are reported independently. **No combined score or overall pass is calculated.**

## Answer similarity

| Model | Rows | Cos N | Cosine mean | Cosine median | Cosine pass | BERT N | BERT P | BERT R | BERT F1 | BERT F1 median | BERT pass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gemma2:2b | 50 | 50 | 0.848 | 0.864 | 0.820 | 50 | 0.890 | 0.932 | 0.910 | 0.904 | 1.000 |
| gemma4:e2b | 50 | 50 | 0.840 | 0.853 | 0.760 | 50 | 0.880 | 0.933 | 0.905 | 0.901 | 0.980 |
| llama3.2:latest | 50 | 50 | 0.817 | 0.848 | 0.740 | 50 | 0.856 | 0.921 | 0.887 | 0.884 | 0.960 |
| phi4-mini:latest | 50 | 50 | 0.802 | 0.802 | 0.640 | 50 | 0.850 | 0.909 | 0.878 | 0.874 | 0.860 |
| qwen2.5:1.5b | 50 | 50 | 0.785 | 0.742 | 0.480 | 50 | 0.864 | 0.904 | 0.883 | 0.873 | 0.900 |

## LLM judge

| Model | N | Correct | Complete | Faithful | Relevant | Pass | Partial | Fail |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gemma2:2b | 50 | 3.680 | 3.680 | 3.680 | 3.820 | 0.900 | 0.040 | 0.060 |
| gemma4:e2b | 50 | 3.440 | 3.500 | 3.600 | 3.560 | 0.820 | 0.080 | 0.100 |
| llama3.2:latest | 50 | 3.200 | 3.200 | 3.340 | 3.420 | 0.760 | 0.100 | 0.140 |
| phi4-mini:latest | 50 | 2.420 | 2.460 | 2.500 | 2.880 | 0.500 | 0.140 | 0.360 |
| qwen2.5:1.5b | 50 | 2.040 | 2.000 | 2.180 | 2.400 | 0.440 | 0.100 | 0.460 |

## Latency and technical failures

| Model | Rewrite ms | Retrieval ms | Generation ms | Judge ms | Total ms | Total median ms | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| gemma2:2b | 0.018 | 168.321 | 2445.811 | 13607.658 | 16881.981 | 15476.825 | 0 |
| gemma4:e2b | 0.023 | 254.767 | 3293.657 | 11149.725 | 15864.783 | 15589.294 | 0 |
| llama3.2:latest | 0.016 | 177.714 | 3338.343 | 11446.828 | 15529.731 | 15536.840 | 0 |
| phi4-mini:latest | 0.043 | 235.092 | 4246.583 | 9056.066 | 14976.813 | 15121.344 | 0 |
| qwen2.5:1.5b | 0.021 | 343.347 | 1772.124 | 16143.447 | 19934.264 | 14984.969 | 0 |

## Question-level diagnostics

| Question | Model | Diagnostics |
|---|---|---|
| `overview-primary-audience` | `llama3.2:latest` | missing gold claim |
| `overview-tailoring-rationale` | `llama3.2:latest` | missing gold claim |
| `core-detect-downstream-support` | `llama3.2:latest` | missing gold claim; unsupported claim; contradiction |
| `core-incident-role-groups` | `llama3.2:latest` | missing gold claim |
| `profiles-preparation-inputs` | `llama3.2:latest` | missing gold claim; unsupported claim |
| `resources-bidirectional-communication` | `llama3.2:latest` | missing gold claim |
| `resources-cybersecurity-privacy-boundary` | `llama3.2:latest` | missing gold claim; unsupported claim |
| `appendix-a-govern-risk-appetite` | `llama3.2:latest` | missing gold claim |
| `appendix-a-identify-asset-priority` | `llama3.2:latest` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-identify-disclosure-process` | `llama3.2:latest` | missing gold claim; contradiction |
| `appendix-a-protect-backup-treatment` | `llama3.2:latest` | missing gold claim; unsupported claim |
| `appendix-a-detect-incident-declaration` | `llama3.2:latest` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-respond-report-triage` | `llama3.2:latest` | missing gold claim; unsupported claim; contradiction |
| `overview-any-organization` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `overview-outcome-prescription` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `overview-primary-audience` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `overview-adoption-paths` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `overview-tailoring-rationale` | `qwen2.5:1.5b` | missing gold claim |
| `core-order-meaning` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `core-detect-downstream-support` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `core-function-timing` | `qwen2.5:1.5b` | missing gold claim |
| `core-incident-role-groups` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `profiles-preparation-inputs` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `resources-online-update-advantage` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `resources-implementation-example-status` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `resources-bidirectional-communication` | `qwen2.5:1.5b` | missing gold claim |
| `resources-cybersecurity-privacy-boundary` | `qwen2.5:1.5b` | missing gold claim |
| `appendix-a-govern-risk-appetite` | `qwen2.5:1.5b` | missing gold claim; unsupported claim |
| `appendix-a-govern-policy-change` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-identify-disclosure-process` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-identify-improvement-sources` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-protect-access-policy` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-protect-backup-treatment` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-respond-report-triage` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-respond-investigation-integrity` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-recover-restoration-assets` | `qwen2.5:1.5b` | missing gold claim; unsupported claim |
| `appendix-a-recover-public-updates` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `glossary-category-meaning` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `glossary-community-profile-characteristics` | `qwen2.5:1.5b` | missing gold claim; contradiction |
| `glossary-reference-guide-distinction` | `qwen2.5:1.5b` | missing gold claim; unsupported claim; contradiction |
| `core-detect-downstream-support` | `gemma2:2b` | missing gold claim; unsupported claim; contradiction |
| `core-incident-role-groups` | `gemma2:2b` | missing gold claim; contradiction |
| `profiles-gap-analysis-output` | `gemma2:2b` | missing gold claim |
| `resources-implementation-example-status` | `gemma2:2b` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-protect-backup-treatment` | `gemma2:2b` | missing gold claim; unsupported claim |
| `overview-outcome-prescription` | `phi4-mini:latest` | missing gold claim; unsupported claim; contradiction |
| `overview-adoption-paths` | `phi4-mini:latest` | missing gold claim |
| `core-order-meaning` | `phi4-mini:latest` | missing gold claim; unsupported claim; contradiction |
| `core-protect-purpose` | `phi4-mini:latest` | missing gold claim; unsupported claim; contradiction |
| `core-detect-downstream-support` | `phi4-mini:latest` | missing gold claim; unsupported claim; contradiction |
| `core-function-timing` | `phi4-mini:latest` | missing gold claim |
| `core-incident-role-groups` | `phi4-mini:latest` | missing gold claim |
| `profiles-gap-analysis-output` | `phi4-mini:latest` | missing gold claim |
| `profiles-tier-role-and-limit` | `phi4-mini:latest` | unsupported claim |
| `resources-implementation-example-status` | `phi4-mini:latest` | missing gold claim; unsupported claim; contradiction |
| `resources-cybersecurity-privacy-boundary` | `phi4-mini:latest` | unsupported claim |
| `appendix-a-govern-risk-appetite` | `phi4-mini:latest` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-govern-policy-change` | `phi4-mini:latest` | missing gold claim; unsupported claim |
| `appendix-a-govern-supplier-risk-lifecycle` | `phi4-mini:latest` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-identify-asset-priority` | `phi4-mini:latest` | missing gold claim; unsupported claim |
| `appendix-a-identify-disclosure-process` | `phi4-mini:latest` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-identify-improvement-sources` | `phi4-mini:latest` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-protect-access-policy` | `phi4-mini:latest` | missing gold claim; unsupported claim |
| `appendix-a-protect-backup-treatment` | `phi4-mini:latest` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-protect-data-states` | `phi4-mini:latest` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-detect-incident-declaration` | `phi4-mini:latest` | missing gold claim; unsupported claim; contradiction |
| `appendix-a-detect-monitoring-analysis` | `phi4-mini:latest` | contradiction |
| `appendix-a-recover-public-updates` | `phi4-mini:latest` | missing gold claim; unsupported claim; contradiction |
| `glossary-category-meaning` | `phi4-mini:latest` | missing gold claim |
| `glossary-example-meaning` | `phi4-mini:latest` | missing gold claim; unsupported claim |
| `glossary-community-profile-characteristics` | `phi4-mini:latest` | unsupported claim |
| `overview-any-organization` | `gemma4:e2b` | missing gold claim; unsupported claim; contradiction |
| `core-order-meaning` | `gemma4:e2b` | missing gold claim; unsupported claim; contradiction |
| `core-detect-downstream-support` | `gemma4:e2b` | missing gold claim; unsupported claim; contradiction |
| `core-function-timing` | `gemma4:e2b` | missing gold claim |
| `resources-implementation-example-status` | `gemma4:e2b` | missing gold claim; unsupported claim; contradiction |
| `resources-reference-scope-variation` | `gemma4:e2b` | missing gold claim |
| `glossary-example-meaning` | `gemma4:e2b` | missing gold claim; unsupported claim; contradiction |

## Interpretation

- Cosine similarity measures embedding agreement with an accepted reference; it does not prove factual correctness.
- BERTScore reports raw token-level semantic precision, recall, and F1. Its pass decision uses F1 only.
- The LLM judge is a consistent rubric-based aid, not a substitute for expert human review.
- Metric pass rates are independent and must not be interpreted as a combined or overall result.
- Each pass rate uses only rows where that metric returned a pass decision; metric counts and technical failures show missing results.
