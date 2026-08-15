
## Final results

| Metric | Llama 3.2 | Qwen 2.5 1.5B |
|---|---:|---:|
| Questions | 20 | 20 |
| Mean cosine similarity | **0.897** | 0.792 |
| Cosine pass rate | **100%** | 50% |
| Judge correctness, 0–4 | **3.10** | 1.75 |
| Judge completeness, 0–4 | **2.90** | 1.80 |
| Judge faithfulness, 0–4 | **3.45** | 1.95 |
| Judge pass rate | **60%** | 40% |
| Evidence hit/recall at 5 | 95% | 95% |
| Mean generation time | 4.49 s | **2.66 s** |
| Technical errors | 0 | 0 |

Conclusion: `llama3.2:latest` produced substantially better answers, while `qwen2.5:1.5b` was about 1.8 seconds faster on average.

Both models had identical retrieval results because the questions were standalone and used the same retriever. The shared retrieval miss was `sp1299-backup-actions`; most other weak answers had the correct evidence available, identifying generation—not retrieval—as the failure source.

## The three techniques in simple words

1. **Cosine similarity**

   It compares the meaning of the generated answer with the correct answer using local embeddings. Higher is more similar. The `0.75` threshold is provisional; cosine alone cannot reliably catch wrong numbers, negation, or MUST/SHOULD changes.

2. **Retrieval evidence coverage**

   It checks whether the retriever found the exact document evidence needed for the answer. `hit@5` means the evidence reached the model; `hit@10` shows whether it was retrieved but ranked too low.

3. **LLM judge**

   Groq `openai/gpt-oss-120b` reads the answer, reference, required claims, evidence, and retrieved context. It scores correctness, completeness, faithfulness, and relevance from 0–4, while listing missing, unsupported, or contradictory claims. Candidate model identity is hidden.
