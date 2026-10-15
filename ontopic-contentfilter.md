# Guardrail V2: On-Topic + Content Filter (ADR-318 / SPEC-223 / PRD-250)

Adds two classifier-based rails on top of the existing V1 PII-only guardrail
(`deploy-guardrail-pii.md`, ADR-309): **`on_topic`** (does this request stay
within tenant-defined topic constraints?) and **`content_filter`** (does it
fall into a blocked content category?). Both run as a bounded LLM call made
*by the gateway itself*, against the tenant's own target model — there is no
new NeMo runtime, no sidecar callback, no platform-owned LLM credential.

**Status as of 2026-07-20**: the whole stack is **landed in `main`** via
reland PR [#2455](https://github.com/futurenestit/xparse/pull/2455) (the
earlier landing attempt #2451 was superseded; PR-2..PR-7 had merged into each
other's stacked bases, not `main`). Two main-only gates surfaced during
landing and were fixed there: (a) the pure-function classifier package was
relocated `xparse_guardrail/engine/llm_classifier/` →
`xparse_guardrail/contract/llm_classifier/` so the INV-202-3 import-lint gate
(caller surfaces may import `client/`/`contract/` only) holds at full
strength; (b) **numbering correction (2026-07-20)**: the guardrail ADR is
**ADR-318** (`docs/adr/ADR-318-guardrail-v2-in-gateway-llm-classifier.md`,
invariants `INV-318-*`); ADR-322 on `main` is the unrelated
credential-drives-provider-in-model-creation decision. An earlier revision of
this document claimed the opposite renumbering — that was wrong. Nothing
below is live in production yet.

**Post-landing follow-up** — PR
[#2456](https://github.com/futurenestit/xparse/pull/2456) (2026-07-20) adds
**SPEC-223 C-223-25**: an `on_topic` trip with no authored
`block_presentation` now presents **gracefully** — HTTP 200,
`finish_reason: content_filter`, assistant content =
`Sorry, I can’t help with that topic because it’s outside my scope.`
(streaming: the message rides the single refusal frame's delta) — instead of
the 451 error envelope. on_topic is a steering rail, not a safety block.
`content_filter` trips originally kept the 451 error default; as of
2026-07-21 (SPEC-223 C-223-27) they present gracefully the same way —
HTTP 200, `finish_reason: content_filter`, assistant content = a
deterministic category message (`self harm related content is forbidden.`,
generic fallback when no category was parsed) — under the same boundaries:
an authored presentation always wins, fail-closed stays 5xx. The default
on_topic message deliberately does **not** echo effective constraints or infer
a keyword from free-form policy text; tenant/admin settings are visible in
Console/effective-policy preview and audit metadata, not to end users. The same
PR ships Console authoring fixes: pinned-model fail-closed warning, empty-list
no-op warnings, input-only copy fix, retryable create chain.

| PR | GitHub | Status | Content |
|---|---|---|---|
| PR-0 | [#2419](https://github.com/futurenestit/xparse/pull/2419) | merged | `docker-compose.pro.yml` gliner fix + `/ready` probe (prerequisite, not V2-specific) |
| PR-1 | [#2424](https://github.com/futurenestit/xparse/pull/2424) | merged | Design closure: PRD-250, ADR-322, SPEC-223, Core cross-refs |
| PR-2 | [#2437](https://github.com/futurenestit/xparse/pull/2437) | merged (stack) | Contract layer: prompt templates, verdict parser, capabilities |
| PR-3 | [#2439](https://github.com/futurenestit/xparse/pull/2439) | merged (stack) | IAM v2 schema + fold operators (write boundary still rejects v2) |
| PR-4 | [#2442](https://github.com/futurenestit/xparse/pull/2442) | merged (stack) | Gateway runtime: the classifier stage itself |
| PR-5 | [#2443](https://github.com/futurenestit/xparse/pull/2443) | merged (stack) | IAM write boundary opens up — v2 authoring becomes possible |
| PR-6 | [#2444](https://github.com/futurenestit/xparse/pull/2444) | merged (stack) | Console authoring UI |
| PR-7 | [#2447](https://github.com/futurenestit/xparse/pull/2447) | merged (stack) | Enforce gate: real latency benchmark vs the NFR budget |
| landing | [#2455](https://github.com/futurenestit/xparse/pull/2455) | merged | Carries PR-2..PR-7 into `main` (supersedes the #2451 attempt); includes the `engine/` → `contract/` relocation and the ADR-318 → ADR-322 renumber |
| follow-up | [#2456](https://github.com/futurenestit/xparse/pull/2456) | merged | C-223-25 on_topic graceful topic refusal + Console authoring UX fixes; PRD-250 A1 amended |
| review fixes | (2026-07-20) | in flight | closes the design-review gaps: classifier policy folded into the semantic-cache key (C-223-20 amended), C-223-26 pre-admission rate guard, masked-text claim corrected (C-223-14 / INV-318-4 / INV-250-2 / N4 amended) |

Tracking issue: [#2446](https://github.com/futurenestit/xparse/issues/2446) —
V2.1, streaming enforce (deferred, see §6).

---

## 1. Why in-gateway, not NeMo

The original idea was to reuse NVIDIA NeMo Guardrails' `on_topic`/self-check
rails. Two things ruled that out:

- ADR-309 (the V1 PII collapse) explicitly decided **against** importing
  `nemoguardrails` into the sidecar (`xparse-guardrails`, ~239MB, 4 light
  deps only: fastapi/uvicorn/httpx/pydantic). Re-adding it would reverse
  that decision without new forces to justify it.
- NeMo's `check_async` needs to call an LLM itself — which would mean either
  giving the sidecar a model credential (a new trust direction the sidecar
  was never designed to hold) or building a sidecar→gateway callback (a new,
  unprecedented trust direction the other way).

The actual capability needed is much smaller than a NeMo runtime: build a
prompt, make one bounded LLM call, parse a one-word verdict. So V2 does that
natively — `xparse_guardrail/contract/llm_classifier/` is pure functions
(prompt builder + parser, zero heavy deps), and the LLM call itself happens
**in the gateway process**, reusing the exact same credential-resolution
path (`KeyResolver` / `WorkerFactory`) the main generation request already
uses. No new secret, no new service, no new trust boundary.

---

## 2. Whose model, whose money

There is a specific business reason the design landed here: Xparse doesn't
provide the LLM — the "target model" is always the tenant's own model
(their OpenAI/Azure/vLLM credential). So the classifier call is not a
platform cost center; it's charged the same way the tenant's own traffic
already is:

- `classifier.model: "auto"` (the default) resolves to
  `execution_plan.assignments[0]` — the actual model the request is about to
  be routed to, **not** the raw `request.model` string the client sent (model
  substitution only rewrites the client-facing name, not the resolved
  assignment — INV-318-6).
- Token usage from the classifier call is metered into the **same tenant
  token budget** as the main generation call (`quota_counter.record()` +
  `schedule_commit()` — the identical pair `non_streaming_handler.py`
  already calls for the main response), and audit-tagged so it's
  distinguishable from generation usage.
- The response is capped at `max_tokens=20` — the verdict is a single word
  (`on-topic`/`off-topic`, `safe`/`unsafe`), so cost per check is small, but
  it is not free, and Console copy should say so.

---

## 3. Policy shape (authoring)

Guardrail policy content is a discriminated union on `version`. V1 (PII-only,
unchanged) has no `version` key required (defaults to `"v1"` on read); V2
adds a `classifier` block:

```json
{
  "version": "v2",
  "engine": "gliner_pii",
  "enabled": true,
  "mode": "shadow",
  "pii": {
    "enabled": true,
    "entities": ["email", "person_name"],
    "action": "mask",
    "score_threshold": 0.5
  },
  "classifier": {
    "model": "auto",
    "on_topic": {
      "enabled": true,
      "constraints": ["Only answer questions about company HR policy."]
    },
    "content_filter": {
      "enabled": true,
      "categories": ["hate", "sexual", "violence", "self_harm", "illegal_activity"],
      "threshold": "medium",
      "stages": ["input"]
    }
  }
}
```

- `classifier.model` — `"auto"` (default) or a specific model name from the
  tenant's model set.
- `on_topic.constraints` — free-text rules, max 32 entries, 500 chars each.
  All must hold (AND) for a request to pass.
- `content_filter.categories` — closed set:
  `hate | illegal_activity | self_harm | sexual | violence`.
- `content_filter.threshold` — `low | medium | high` (ordered lattice; `low`
  blocks the most, i.e. is strictest).
- `content_filter.stages` — `input`, `output`, or both. **Output enforcement
  is non-streaming only in this campaign** — see §6.
- `mode` — `shadow` (detect + audit, never block) or `enforce` (block on
  violation, fail-closed on timeout/unparseable). Same field V1 already
  uses; still defaults to `shadow`.

### Inheritance (bundle fold, PRD-204)

Same monotonic-tightening model as everything else in the policy system —
a child scope can only make things stricter, never looser:

| Field | Fold operator |
|---|---|
| `on_topic.constraints` | set-union (more rules = stricter) |
| `content_filter.categories` | set-union |
| `content_filter.threshold` | min of the ordered lattice (`low` wins) |
| `content_filter.stages` | set-union |
| `classifier.model` | **ancestor pin wins** — the opposite direction from `engine`'s child-overrides. A child scope cannot override an ancestor's non-`"auto"` pin; two conflicting non-`"auto"` pins at the same scope is a hard reject. |
| classifier block presence | either side having one wins (opt-in only tightens) |

A bundle whose fold never received a `classifier` contribution from any
layer downgrades cleanly to a plain v1 payload on the wire — a gateway that
doesn't yet understand v2 (i.e. hasn't deployed PR-4) still gets a v1 shape
it already knows how to parse. This is why PR-4 (gateway parses v2) must
deploy before PR-5 (IAM allows authoring v2) — but note the failure mode the
ordering prevents (corrected 2026-07-20): the gateway's snapshot `spec` is a
raw dict, so a pre-V2 gateway that DOES receive an authored-v2 snapshot does
**not** pydantic-hard-fail — its adapter tolerantly returns `classifier=None`
and the policy **silently degrades to PII-only** (fail-open for the new
rails). Gateway-first ordering exists to prevent that silent degradation,
not a loud crash.

---

## 4. Runtime workflow

```
Client
  │
  ▼
Gateway: authenticate
  │
  ▼
V1 PII input guardrail (pre-routing, unchanged)   ← classifier sees masked text ONLY when the
  │                                                  PII rail is enforce+modify; PII shadow does
  │                                                  not mutate, so the classifier sees the same
  │                                                  raw text the provider gets (C-223-14)
  ▼
Semantic cache lookup                             ← classifier policy is part of the cache key
  │                                                  (C-223-20): a hit is always same-policy, so
  │                                                  skipping re-evaluation is sound
  │                                                  (audit gets guardrail_classifier_skipped=cache_hit)
  ▼
Request policy → routing → evaluate_execution_policy
  │
  ▼
★ Classifier stage (bustream/gateway/classifier_handler.py) ★
  │   C-223-26 rate guard: per-principal auxiliary token bucket consumed BEFORE
  │     any LLM dispatch (exhausted → enforce 429 / shadow skip+audit) — the
  │     pre-admission placement is no longer an unmetered provider-call path
  │   on_topic check ─┐
  │   content_filter ─┤─ run concurrently (asyncio.gather)
  │                    │
  │   enforce mode: fail-closed on timeout/unparseable verdict, blocks synchronously
  │     · on_topic trip → 200 graceful refusal with the generic topic message (C-223-25, #2456)
  │     · content_filter trip → 200 graceful refusal with the category message (C-223-27)
  │   shadow mode:   fire-and-forget, +0ms client-visible latency, audit only
  │
  ▼
Admission → lease → model substitution → generation
  │
  ▼
Non-streaming output: content_filter(output) enforced same as input (if configured)
Streaming output: shadow/audit only in V2 — see §6
  │
  ▼
Audit: one GUARDRAIL_INPUT_CHECK / GUARDRAIL_OUTPUT_CHECK event PER check that ran
       (check_type ∈ {pii, on_topic, content_filter}; never raw content)
```

The classifier call itself (`_call_classifier_llm` in `classifier_handler.py`):
build the prompt (`prompt_templates.py`) → resolve the target model + its
existing credential (`_resolve_classifier_target`, DB-first, **no YAML
fallback** — a known footgun elsewhere in this codebase, deliberately not
repeated here) → run it through the same `WorkerFactory`/`BaseWorker.stream()`
path generation uses → parse the one-word verdict (`parser.py`, exact-match,
fails loud on garbage) → meter usage → emit audit.

---

## 5. Enforce-gate results (PR-7)

Real benchmark (`scripts/benchmark_classifier_latency.py`) against a real
gateway pipeline and real `gpt-4o-mini` as the target model, 114 round trips
per check:

| Check | p50 | p95 | Budget (SPEC-223 NFR) |
|---|---|---|---|
| `on_topic` | ~740ms | ~1.2–1.4s | ≤ 1500ms — **pass** |
| `content_filter` | ~700-730ms | ~1.17s | ≤ 1500ms — **pass** |

Passing this gate means enforce mode is technically viable — it does **not**
mean any tenant should be flipped to `enforce` yet. A real false-positive
(would-block) rate needs real production shadow traffic, which doesn't
exist pre-deployment; ADR-322 §7.3 documents the exact audit query to run
once shadow data accumulates, rather than fabricating a number. The default
stays `shadow`.

---

## 6. Known gaps / explicitly deferred (not silently dropped)

- **Streaming output enforcement** — the dormant ADR-303 buffer-then-emit
  hooks are not re-activated for the V2 classifier; streamed responses only
  get shadow/audit coverage for `content_filter` on the output side.
  Non-streaming output enforcement is fully wired. Tracked as
  [issue #2446](https://github.com/futurenestit/xparse/issues/2446) (V2.1).
- **No dry-run/preview endpoint for the classifier.** Both existing preview
  surfaces — `POST /iam/guardrails/dry-run` (authoring-time) and
  `POST /v1/guardrails/preview` (runtime, via API key) — are still V1
  PII-only; neither runs `on_topic`/`content_filter`. A saved+bound v2
  policy works correctly on real traffic (that's what PR-4/PR-7 verify),
  but there is no "test my topic rules against a sample before saving" UX
  yet, and the Console form (PR-6) doesn't call anything like it. Not
  scoped into this campaign; would be a natural follow-up if wanted.
- **Console "clamps advisory" UI** (showing an ancestor's clamp visually
  before a child tries to loosen it) is deferred for the v2 fields
  specifically, per PR-6's scope note.
- **`block_presentation` is not authorable on v2 kind policies.** SPEC-213's
  `error | graceful` presentation ladder exists in the gateway, but the v2
  policy spec has no `presentation` field and the kind-snapshot adapter
  doesn't carry one — so a v2 author cannot force a trip BACK to the `error`
  presentation. Both classifier rails now default to graceful 200 (on_topic
  by C-223-25, content_filter by C-223-27 as of 2026-07-21), so the remaining
  gap is the *override* direction only. Recommended follow-up: add a top-level
  presentation field to the v2 spec + IAM validation + adapter passthrough +
  Console select, keeping the graceful classifier defaults.

---

## 7. Complete file map

### PR-0 — prerequisite fix (merged, #2419)

| File | Type | What |
|---|---|---|
| `install_service/tiers/docker-compose.pro.yml` | modified | add `xparse-gliner` service, fix stale env vars so the `pro` tier's guardrails profile actually starts |
| `xparse_guardrail/server/app.py` | modified | `GET /ready` — probes the GLiNER server is reachable, not just process-alive |
| `xparse_guardrail/tests/server/__init__.py` | new | test package init |
| `xparse_guardrail/tests/server/test_ready_probe.py` | new | 4 tests against a real local `HTTPServer` |

### PR-1 — design closure (merged, #2424)

| File | Type | What |
|---|---|---|
| `docs/prd/PRD-250-guardrail-v2-topic-and-content-category-controls.md` | new | business requirements |
| `docs/adr/ADR-322-guardrail-v2-in-gateway-llm-classifier.md` | new | architecture decision, invariants INV-318-1..9, enforce-gate results (§7.3 added in PR-7) |
| `docs/specs/SPEC-223-guardrail-v2-contract.md` | new | normative contract, C-223-1..24 |
| `docs/adr/core/Core-ADR-02-Policy-Authorization.md` | modified | Core integration layer cross-reference |
| `docs/prd/core/Core-PRD-02-Policy-Authorization.md` | modified | Core integration layer cross-reference |
| `docs/adr/ADR-303-guardrail-output-path-coverage.md` | modified | amended-by annotation |
| `docs/adr/ADR-309-guardrail-v1-gliner-pii-collapse.md` | modified | amended-by annotation |
| `docs/research/nemo-guardrails/v2-classifier-addendum.md` | new | prompt provenance (NeMo self-check templates, attribution) + PR-2 probe transcript |
| `docs/research/研究智庫-HUB.md` | modified | research registry entry |
| `xparse-wiki/wiki/concepts/guardrail-enforcement.md` | modified | wiki sync |

### PR-2 — classifier contract layer (open, #2437)

| File | Type | What |
|---|---|---|
| `xparse_guardrail/contract/verdict.py` | modified | additive `ClassifierFlag`, `classifier_flags`/`classifier_score` on `GuardrailVerdict` |
| `xparse_guardrail/contract/capabilities.py` | modified | `SUPPORTED_CONTENT_CATEGORIES`, `llm_classifier` engine descriptor, `validate_classifier_profile_against_engine()` |
| `xparse_guardrail/contract/llm_classifier/__init__.py` | new | package exports |
| `xparse_guardrail/contract/llm_classifier/prompt_templates.py` | new | `build_topic_prompt()`, `build_content_prompt()` — pure functions |
| `xparse_guardrail/contract/llm_classifier/parser.py` | new | `parse_topic_verdict()`, `parse_content_verdict()` — exact-match, fail-loud |
| `scripts/probe_llm_classifier.py` | new | §8.1 real-component probe against a real model |
| `xparse_guardrail/tests/llm_classifier/__init__.py` | new | test package init |
| `xparse_guardrail/tests/llm_classifier/test_prompts_and_parser.py` | new | ~70 tests |
| `docs/research/nemo-guardrails/v2-classifier-addendum.md` | modified | filled in with real probe transcript/results |

### PR-3 — IAM schema + fold (open, #2439; write boundary still v1-only)

| File | Type | What |
|---|---|---|
| `xparse_iam/xparse_iam/policies/schema.py` | modified | `GuardrailTopicSpec`, `GuardrailContentFilterSpec`, `GuardrailClassifierSpec`, `GuardrailPolicySpecV2`, discriminated union `GuardrailPolicySpecAny` |
| `xparse_iam/xparse_iam/policies/__init__.py` | modified | export the new v2 types |
| `xparse_iam/xparse_iam/authorization/guardrail_policy_merge.py` | modified | `_as_v2`/`_downgrade_if_v1_only` (total, never-raises), v2 fold operators, clamps |
| `xparse_iam/xparse_iam/authorization/guardrail_resolver.py` | modified | `classifier.model` same-scope placement conflict assertion, capability re-assert |
| `xparse_iam/tests/unit/test_guardrail_policy_merge_v2.py` | new | 18 tests, fold monotonicity/placement/downgrade |
| `xparse_iam/tests/integration/test_bundle_item_fold_resolver.py` | modified | `TestGuardrailV2ClassifierFold` class, 6 tests, real resolver |
| `xparse_iam/tests/integration/test_validate_policy_content.py` | modified | intentional tripwire (replaced in PR-5) |
| `xparse_guardrail/tests/contract/test_capabilities.py` | modified | capability descriptor tests |
| `docs/adr/ADR-322-...md`, `docs/specs/SPEC-223-...md` | modified | wording refinements discovered during implementation (empty-classifier-block nuance) |

### PR-4 — gateway runtime (open, #2442) — largest PR

| File | Type | What |
|---|---|---|
| `bustream/gateway/classifier_handler.py` | new (~920 lines) | the stage itself: target resolution, worker call, concurrent on_topic+content_filter evaluation, quota metering, per-check audit emission, shadow dispatch |
| `bustream/gateway/routes/chat.py` | modified | insertion point right before admission, cache-hit audit marker |
| `bustream/gateway/non_streaming_handler.py` | modified | wires `run_output_classifier()` after the existing PII output check |
| `bustream/gateway/cache_handler.py` | modified | `guardrail_classifier_skipped` marker on cache hit |
| `bustream/gateway/guardrail_policy_adapter.py` | modified | `_classifier_from_spec()` — v2 snapshot parsing |
| `bustream/gateway/iam_http_client.py` | modified | `HttpGuardrailClassifierData`, `classifier` field on the policy snapshot |
| `bustream/gateway/guardrail_response.py` | modified | 4 new fail-closed reason codes |
| `tests/unit/test_classifier_handler.py` | new | 22 tests, real-delay fake worker (§8.1: fake simulates the dependency, not the orchestrator) |
| `tests/unit/test_gateway_cache_handler.py` | modified | +2 tests |
| `tests/unit/test_guardrail_kind_runtime.py` | modified | +4 v2 adapter tolerance tests |

### PR-5 — IAM write boundary flip (open, #2443)

| File | Type | What |
|---|---|---|
| `xparse_iam/xparse_iam/application/use_cases/policy/validate_policy_content.py` | modified | accepts `GuardrailPolicySpecAny` (v1 or v2) at the write boundary; capability-gates `content_filter.categories`/`stages` |
| `xparse_iam/tests/integration/test_validate_policy_content.py` | modified | tripwire replaced with 10 real v2 tests |
| `xparse_iam/tests/integration/test_guardrail_validate_e2e.py` | modified | real write validator → real resolver → real gateway adapter, end to end |

### PR-6 — Console authoring UI (open, #2444)

| File | Type | What |
|---|---|---|
| `frontend/console-app-refactor/src/types/iam.ts` | modified | `GuardrailContentCategory`, `VersionedGuardrailClassifierSpec`, etc. |
| `.../policies/_components/policy/policy-content-form.tsx` | modified | `TopicConstraintsEditor`, `ClassifierSettings` components; `buildGuardrailContent()`/`guardrailFormFromContent()` widened |
| `.../policies/_components/policy/policy-content-form.test.ts` | modified | +9 tests |

### PR-7 — enforce gate (open, #2447)

| File | Type | What |
|---|---|---|
| `scripts/benchmark_classifier_latency.py` | new | real p50/p95 latency benchmark vs the SPEC-223 NFR budget |
| `docs/adr/ADR-322-...md` | modified | §7.3 — measured results, honest shadow would-block scope note, streaming-enforce deferral |
| `docs/specs/SPEC-223-...md` | modified | NFR budget table filled in with real numbers |

---

## 8. Related, not modified

- V1 PII guardrail — unchanged, see `deploy-guardrail-pii.md`.
- `bustream/streaming/manager_v3_events.py` (ADR-303 buffer hooks) — read
  but not touched; V2.1 will wire into it.
- `docker-compose.mvp.yml` (repo root) — the actual compose file for local
  dev; `install_service/tiers/docker-compose.pro.yml` (PR-0) is the packaged
  installer's tier config, a separate file with separate defaults.
