# Deploying the Guardrail PII Feature (GLiNER, ADR-309)

How to deploy the V1 PII-only guardrail — what changed from the old NeMo
guardrail, what (if anything) goes in `.env`, and how to verify the chain.

**TL;DR for local dev: nothing to add to `.env`. Just run `./dev.sh guardrails`.**

---

## 1. Architecture (what you are deploying)

```
Client → Gateway (guardrail_enforcer)
             │  POST /v1/guardrails/check          XPARSE_GUARDRAIL_SIDECAR_URL
             ▼
         xparse-guardrails :8400   (sidecar shim, ~239MB)
             │  POST /extract                      XPARSE_GLINER_SERVER_URL
             ▼
         xparse-gliner     :8401   (GLiNER detector, ~3.7GB, model baked in,
                                    runs air-gapped: HF_HUB_OFFLINE=1)
```

Two containers, both behind the `guardrails` compose profile — they do NOT
start with the plain stack. If the gateway can't reach the sidecar while a
policy is in `mode: enforce`, requests are **blocked fail-closed** with
HTTP 451 `engine_error` (INV-309-6). This is by design, not a bug.

---

## 2. What changed vs the old (NeMo) guardrail

| | Old (NeMo, ADR-139) | New (GLiNER PII, ADR-309) |
|---|---|---|
| Detection | NeMo judge LLM — needed an external OpenAI-compatible endpoint | Self-hosted GLiNER server; no external calls, no API key |
| Required `.env` vars | `XPARSE_GUARDRAIL_JUDGE_BASE_URL`, `XPARSE_GUARDRAIL_JUDGE_API_KEY` | **none** |
| Containers | `xparse-guardrails` only | `xparse-guardrails` **+ `xparse-gliner`** (new) |
| Engine default | `nemo` | `gliner_pii` (env `XPARSE_GUARDRAIL_ENGINE` — leave unset) |
| Mode authority | env `XPARSE_GUARDRAIL_MODE` | **per-policy in Console** (`mode: shadow\|enforce` in the policy JSON); env is only a legacy fallback (#1712) |
| Capabilities | content filter levels + keywords + PII | PII mask only (12 entity types, `score_threshold`) |

**Cleanup**: if a `.env` still has `XPARSE_GUARDRAIL_JUDGE_BASE_URL` /
`XPARSE_GUARDRAIL_JUDGE_API_KEY`, they are dead after ADR-309 PR-7 and can be
deleted. (The note printed by `dev.sh` about judge vars for low/medium/high
content safety is stale — those rails were retired.)

---

## 3. Local dev deployment

### 3.1 `.env` — nothing required

All wiring has correct compose defaults:

| Env var | Default | Set only when… |
|---|---|---|
| `XPARSE_GUARDRAIL_SIDECAR_URL` (gateway + IAM) | `http://xparse-guardrails:8400` | sidecar runs on another host |
| `XPARSE_GLINER_SERVER_URL` (sidecar) | `http://xparse-gliner:8401` | detector runs elsewhere, e.g. a GPU box |
| `XPARSE_GUARDRAIL_TIMEOUT_SEC` (gateway) | `5.0` | CPU latency makes enforce-mode checks time out (see §6) |
| `XPARSE_GLINER_IMAGE` | `xparse-gliner-server:probe` | pinning a different local detector image |

### 3.2 Start

```bash
cd /Users/peter/Desktop/X-parse/xparse

./dev.sh guardrails      # add sidecar + detector to a running stack
# or
./dev.sh up-guardrails   # full stack + guardrails in one shot
```

Both commands also wait for the detector health check and run a PII warmup
call (first GLiNER inference is slow; without warmup the first guarded
request may hit `engine_timeout`).

### 3.3 Verify

```bash
# 1. Both containers healthy
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'guardrails|gliner'

# 2. Sidecar health
docker exec xparse-guardrails python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8400/health').read().decode())"

# 3. End-to-end mask check (should return action=modify with [EMAIL_1] mask)
docker exec xparse-guardrails python -c "import json, urllib.request; \
p={'stage':'input','text':'mail me at test@example.com','engine_id':'gliner_pii', \
'profile':{'pii_redaction_enabled':True,'pii_entities':['email'],'pii_score_threshold':0.5}}; \
r=urllib.request.Request('http://127.0.0.1:8400/v1/guardrails/check', \
data=json.dumps(p).encode(), headers={'content-type':'application/json'}, method='POST'); \
print(urllib.request.urlopen(r, timeout=30).read().decode())"
```

Then send a real chat request through an app whose bound policy has
`pii.enabled: true`. In `shadow` mode the response is untouched but
`docker logs xparse-gateway | grep guardrail` shows the verdict; in
`enforce` mode PII in the input is masked before reaching the provider.

---

## 4. Policy configuration (Console, not env)

The behavior switch lives in the guardrail policy JSON, not in `.env`:

```json
{
  "version": "v1",
  "engine": "gliner_pii",
  "enabled": true,
  "mode": "shadow",
  "pii": {
    "enabled": true,
    "entities": ["email", "person_name", "phone", "address", "gender"],
    "action": "mask",
    "score_threshold": 0.5
  }
}
```

- `mode: shadow` — detect + audit, never block/mask. **Start here.**
- `mode: enforce` — mask input PII; block (451) if the engine is unreachable.
- `score_threshold` — GLiNER confidence cutoff, keep `0.5` until shadow-mode
  audit data justifies tuning. Deterministic regex hits (TW ID, phone
  formats…) score 1.0 and ignore this knob.

---

## 5. Production (cloud / enterprise compose)

Same two images from ECR (`xparse-guardrails`, `xparse-gliner-server`), same
profile gate:

```bash
docker compose -f docker-compose.cloud.yml --profile guardrails up -d \
  xparse-gliner xparse-guardrails
```

Notes:

- Compose defaults already point gateway → sidecar → detector; only override
  the two URL vars for split-host topologies.
- **Do not flip tenant policies to `enforce` on CPU hosts without probing
  latency first** (`scripts/probe_gliner_pii.py`). CPU baseline measured
  p50 ≈ 2.2s for 1KB input, ≈ 19s for 8KB — enforce mode needs GPU or tuned
  chunking, otherwise guarded requests exceed the 5s gateway timeout and
  fail closed. Shadow mode is the rollout guardrail (ADR-309 R2).
- After changing `.env`, re-run `docker compose up -d` (recreate); plain
  `docker restart` does not re-read `.env`.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| 451 `engine_error` | Sidecar not running / DNS `xparse-guardrails` unresolvable | `./dev.sh guardrails`; check `docker ps` |
| 451 `engine_timeout` | Cold model (no warmup) or CPU latency > 5s | Re-run warmup (§3.3 step 3); raise `XPARSE_GUARDRAIL_TIMEOUT_SEC`; use shadow mode |
| PII passes through untouched | Policy `mode: shadow` (expected), or `pii.enabled: false`, or entity type not selected | Check the bound policy JSON in Console |
| Chinese names not masked | Fixed via CJK shadow-text in gliner-server — requires a current `xparse-gliner-server` image | Rebuild/pull the detector image |
| First request after stack start is slow | Model load + first inference | Keep the `dev.sh` warmup; it exists for this |
