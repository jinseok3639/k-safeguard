<div align="center">

# k-safeguard

**A normalizer that turns obfuscated Korean back into the original text**

[![Python package](https://github.com/jinseok3639/k-safeguard/actions/workflows/package.yml/badge.svg)](https://github.com/jinseok3639/k-safeguard/actions/workflows/package.yml)
[![Branch coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/jinseok3639/k-safeguard/badges/branch-coverage.json&cacheSeconds=300)](https://github.com/jinseok3639/k-safeguard/actions/workflows/coverage.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/jinseok3639/k-safeguard/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](https://github.com/jinseok3639/k-safeguard/blob/main/pyproject.toml)

[한국어](https://github.com/jinseok3639/k-safeguard/blob/main/README.md) · **English** &nbsp;|&nbsp; [Benchmark dataset](https://huggingface.co/datasets/kimchunsik03/KoreanGuardrail) · [Experiments repository](https://github.com/jinseok3639/k-safeguard-ML-experiment)

[Try it in your browser](https://jinseok3639.github.io/k-safeguard/) — a normalization playground that never sends your input to a server · [API docs (Korean)](https://jinseok3639.github.io/k-safeguard/docs/)

</div>

---

## Why this exists

Korean stays easy for people to read when its jamo are split apart or spelled the way it sounds, but software sees a different string.
Search, filters, classifiers, and language models miss the original meaning. k-safeguard restores the text so it can sit in front of them.

```python
from k_safeguard import Gateway

Gateway().normalize("ㅅㅣㅅㅡㅌㅔㅁ 점검")     # → "시스템 점검"
```

## Installation

```bash
python -m pip install k-safeguard
```

The base install has **no runtime dependencies.** It does not pull in Torch, Transformers, or any model weights, so it drops into an existing service as-is.

The context-aware restoration model is a separate extra: `k-safeguard[ml-restore]` (`onnxruntime`, `numpy`, `tokenizers`). It downloads about 500 MB of weights on first use and is never attached to the default Gateway.

## Quick start

### 1. Rule-based normalization

Reverses only what can be determined with certainty, with no extra dependencies.

```python
from k_safeguard import Gateway

assert Gateway().normalize("ㅇㅏㄴㄴㅕㅇ") == "안녕"
```

### 2. Restoring with the model

Also reverses variants that need context, such as tensification, resyllabification, and coda changes.

```python
from k_safeguard import Gateway
from k_safeguard.providers.ml_restore import MlRestoreProvider

gateway = Gateway(providers=[MlRestoreProvider.from_pretrained()])
gateway.normalize("요리 만뜨는 뻡 알려쭤")
```

### 3. Inspecting candidates

`process()` returns the original, the normalized text, and every restoration candidate.

```python
result = Gateway().process("ㅇㅏㄴㄴㅕㅇ")

assert result.views[0].text == "ㅇㅏㄴㄴㅕㅇ"     # the original always comes first
assert result.normalized == "안녕"
```

Runnable examples live in [`examples/`](https://github.com/jinseok3639/k-safeguard/blob/main/examples/README.md) (Korean comments).

## How it works

```text
input
 │
 ├─ lossless normalization   reverses only what can be determined with certainty
 │
 ├─ providers (opt-in)       produce restoration candidates from models or rules
 ▼
normalize() → one normalized sentence
process()   → original, normalized text, and candidates
evaluate()  → classifies the whole list (guardrail integration)
```

The governing design rule is that **the original text is never lost.** Tensification cannot be restored losslessly, so
the default Gateway leaves it unchanged; only the opt-in model restores it, as a separate candidate.

### Default normalization rules (lossless)

| rule ID | Target | Policy |
|---|---|---|
| `remove_hangul_zwsp` | U+200B adjacent to Hangul syllables or jamo | Remove just that character |
| `compose_modern_jamo` | Modern conjoining jamo sequences such as `안` | Compose into a syllable |
| `compose_compat_jamo` | Compatibility jamo sequences such as `ㅇㅏㄴ` | Compose after checking the following vowel boundary |

Global NFC is deliberately not applied; only modern Hangul jamo sequences are composed. That keeps emoji ZWJ sequences, combining marks, and Korean–English code-switched input intact. See the [normalizer document](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/NORMALIZER.md) (Korean) for details.

### Ambiguous-variant policy

Tensification cannot be restored to one original string without context. Experiments that OR-ed
multiple candidates into a guardrail increased false positives, so its candidate provider is no longer
part of the public API, and the deployed Gateway does not create multiple restoration views for it.
The candidate-generation code has been removed; its history remains at commit `b000d24`.

## Measured results

### Restoration model

Measured on evaluation set v1 through the same path as `Gateway` (lossless normalization, then one sentence at a time on CPU onnxruntime): 13,344 sentences containing only restorable types, plus 695 source sentences, all produced by the project's own generator.

| Metric | Result |
|---|---:|
| Character-level F1 | **85.2%** |
| Per-sentence restoration rate | 78.9% |
| Fully restored / made worse | 45.6% / 1.0% |
| Clean-sentence mutation | 0.72% (5/695) |
| Latency p50 / p95 (CPU) | 13 ms / 18 ms |

## Use case: in front of a guardrail

One common use is stopping input that evades a prompt guardrail through obfuscation.
Running 505 independent seeds (301 attacks / 204 benign) through `kakaocorp/kanana-safeguard-prompt-2.1b` shows detection collapsing on spelling changes alone.

| Input | Attack block rate |
|---|---:|
| Standard orthography (no obfuscation) | **94.02%** |
| Tensification, intensity 1.0 — prompt injection (A1) | 10.31% |
| Tensification, intensity 1.0 — prompt leaking (A2) | 20.56% |

Status: `PROVISIONAL_DEV_ONLY`. These come from the public development benchmark and must not be read as locked-test performance ([run `tensify-impact-v1-20260811`](https://github.com/jinseok3639/k-safeguard/blob/f6ee374/experiments/benchmark/TENSIFY_GUARDRAIL_IMPACT.md), Korean).

k-safeguard is one defensive layer, not a complete solution to guardrail evasion.

`evaluate()` passes the original and the normalized views to your classifier and blocks if any of them is flagged. The verdict comes from your guardrail, not from k-safeguard.

```python
decision = Gateway().evaluate("user input", lambda text: guardrail(text).blocked)

if decision.block:
    raise PermissionError("guardrail blocked")

decision = await Gateway().evaluate_async("user input", async_classifier)

decision = Gateway().evaluate_batch(
    "user input",
    lambda texts: [item.blocked for item in guardrail.classify_batch(texts)],
    batch_size=4,
)
```

See the [execution and aggregation API](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/EXECUTION.md) (Korean) for error policy and traces.

### Guardrail evaluation

These results are for rule-based normalization. Guardrail recovery of the current model has not been measured yet.

Every number below is reproducible against the 5,555-row benchmark derived from 505 independent seeds, using pinned model revisions.

| Check | Result |
|---|---|
| Exact string restoration, jamo decomposition and ZWSP | 505/505 (at intensity 0.5 and 1.0 each) |
| Clean mutation rate | 0% — all 505 clean rows left unchanged |
| End-to-end recovery smoke (live Kanana calls) | 4/4 obfuscated fixtures went from raw allow → blocked on the normalized view |
| Batch inference | Verdict parity held across 20 views; 90% fewer calls and 74.3% less wall time |

> **Interpretation limits**: the end-to-end smoke test uses fixtures deliberately selected for known recovery, so it is a regression check and must not be read as a population-level performance estimate.
> Of the full E0/E1/E2/E3 evaluation, only the prompt guardrail verdicts are valid. Downstream LLM intent recognition, semantic fidelity, and actual attack success remain `INCOMPLETE`.
> The metric definitions live in [EVALUATION_SPEC](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/EVALUATION_SPEC.md) and the run procedure in the [normalization evaluation document](https://github.com/jinseok3639/k-safeguard/blob/f6ee374/experiments/benchmark/NORMALIZER_EVALUATION.md) (both Korean).

## Scope and limits

**In scope** — normalizing Korean orthographic obfuscation: jamo decomposition, tensification, resyllabification, coda cramming, spacing destruction, symbol insertion, and zero-width characters.

**Limits**

- The model is weak on shapes absent from training. On sentences from other generators (KOTOX, kotka), character-level F1 is 63.0% and the per-sentence restoration rate is 53.8%.
- The model can change clean sentences, mostly loanwords and technical terms. When the original matters, use `process()` and keep it alongside.
- The evaluation sentences do not represent general text; other domains such as news or community posts have not been measured.
- Loading the model adds about 520 MB of memory. Long input is restored up to about 12,000 characters (384 × 32 chunks); the rest stays unchanged.

**Out of scope**

- Chosung (initial-consonant) abbreviation — keeping only initial consonants erases most of the text, so it is left unchanged
- Other-language spellings and multimodal input
- Verdicts — k-safeguard never decides block or allow on its own

## What ships alongside

| Artifact | Location | Description |
|---|---|---|
| Runnable examples | [`examples/`](https://github.com/jinseok3639/k-safeguard/blob/main/examples/README.md) | Sample code: normalization, provider extension, guardrail wiring, async/batch, error policy |
| Obfuscation generator | [`k_safeguard.obfuscate`](https://github.com/jinseok3639/k-safeguard/blob/main/src/k_safeguard/obfuscate.py) | 24 techniques with intensity and seed control, for testing the normalizer or building evaluation data. Look-alike dictionary from [KOTOX](https://github.com/leeyejin1231/KOTOX) (MIT) |
| Benchmark dataset | [HF: KoreanGuardrail](https://huggingface.co/datasets/kimchunsik03/KoreanGuardrail) | 505 seeds → 5,555 derived rows. Data under CC-BY-4.0 |
| Experiments | [k-safeguard-ML-experiment](https://github.com/jinseok3639/k-safeguard-ML-experiment) | Restoration and guardrail experiment runners with recorded results |

## Documentation

All documents are written in Korean.

| Document | Contents |
|---|---|
| [NORMALIZER](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/NORMALIZER.md) | Normalization rules, supported range, benchmark verification |
| [EXECUTION](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/EXECUTION.md) | Classifier execution and aggregation API, error policy, traces |
| [PACKAGING](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/PACKAGING.md) | Package layout, provider boundaries, release verification |
| [EVALUATION_SPEC](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/EVALUATION_SPEC.md) | Metric definitions and reporting rules |
| [KOREAN_OBFUSCATION_RESEARCH](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/KOREAN_OBFUSCATION_RESEARCH.md) | Taxonomy of Hangul obfuscation techniques and prior-art survey |

## Development

```bash
python -m pip install -e ".[dev,mutation]"
python -m unittest discover -s tests
python -m coverage run -m unittest discover -s tests && python -m coverage report    # branch coverage
mutmut run && mutmut results    # mutation testing
```

Branch and commit conventions follow the [Git workflow in AGENTS.md](https://github.com/jinseok3639/k-safeguard/blob/main/AGENTS.md#git-워크플로): `type(scope): Korean description`, with one PR per feature or experiment.

For bug reports and enhancement proposals, use the [issue templates](https://github.com/jinseok3639/k-safeguard/issues/new/choose). See [CONTRIBUTING.md](https://github.com/jinseok3639/k-safeguard/blob/main/CONTRIBUTING.md) (Korean) for the full contribution process.

## License

Code under [Apache License 2.0](https://github.com/jinseok3639/k-safeguard/blob/main/LICENSE); the benchmark dataset under CC-BY-4.0; the model weights fetched by `from_pretrained()` under CC BY-SA 4.0 ([sources and notices](https://github.com/jinseok3639/k-safeguard/blob/main/tools/release/WEIGHTS_LICENSE.md)). The weights are not part of the wheel. The lookalike dictionary bundled in the package comes from KOTOX under MIT.
