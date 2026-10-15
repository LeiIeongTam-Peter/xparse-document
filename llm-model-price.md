# LLM Model Pricing Enrichment

Date: 2026-07-02

This document explains the LLM model pricing work added to Xparse IAM, including
the create-model workflow, external pricing sources, fallback behavior, backfill
path, and files changed or created.

## Goal

When a user creates a model through the LLM Proxy model flow, IAM should try to
fill these pricing fields automatically:

- `cost_per_input_token`
- `cost_per_output_token`

The stored unit is USD per token. The Console displays these values as `$ /M` by
multiplying the stored value by `1,000,000`.

Example:

```text
0.000005 USD/token * 1,000,000 = 5 $/M
0.00003 USD/token * 1,000,000 = 30 $/M
```

The enrichment is best-effort. If every pricing source fails or no matching
catalog entry exists, model creation still succeeds and pricing remains `NULL`.

## Create Model Workflow

User-facing request path:

```text
POST /apis/iam/groups/{group_uuid}/models
```

Internal route:

```text
POST /iam/groups/{group_uuid}/models
```

Workflow:

1. IAM validates the create request:
   - provider exists and is active
   - `(group_uuid, provider, model_name)` is unique
   - credential belongs to the group scope when provided
   - provisioner is a valid LLM Proxy application when provided

2. If the request already includes both `cost_per_input_token` and
   `cost_per_output_token`, IAM does not call external pricing catalogs.

3. If either price is missing, IAM builds a pricing lookup identity:
   - provider: `pricing_provider` override, otherwise `provider`
   - model: `pricing_model` override, otherwise `served_model_name`, otherwise
     `model_name`

4. The pricing resolver tries configured sources in order:

   ```text
   Alias layer -> Portkey -> LiteLLM -> OpenRouter
   ```

5. If a price is found, IAM stores it on the `Model` row:
   - `Model.cost_per_input_token`
   - `Model.cost_per_output_token`

6. If the model is created and immediately bound to an LLM Proxy, the same
   prices are copied to the binding row:
   - `ApplicationModel.cost_per_input_token`
   - `ApplicationModel.cost_per_output_token`

7. If lookup fails, IAM leaves the price fields empty and still creates the
   model.

## External Pricing Sources

### 1. Portkey

HTTP API:

```text
GET https://api.portkey.ai/model-configs/pricing/{provider}/{model}
```

Example:

```text
GET https://api.portkey.ai/model-configs/pricing/openai/gpt-4o
```

Portkey returns prices as cents per token. Xparse stores USD per token, so the
resolver divides Portkey values by `100`.

Example:

```text
Portkey request_token.price = 0.00025 cents/token
Xparse stores 0.00025 / 100 = 0.0000025 USD/token
Console shows 0.0000025 * 1,000,000 = 2.5 $/M
```

### 2. LiteLLM

LiteLLM is used as an optional local Python registry, not as an HTTP API.

Used APIs:

```python
from litellm import get_llm_provider
litellm.model_cost
```

The resolver reads:

- provider from `get_llm_provider(model_name)`
- input price from `model_cost[model]["input_cost_per_token"]`
- output price from `model_cost[model]["output_cost_per_token"]`

LiteLLM is optional. If it is not installed, the resolver logs the miss and
continues to OpenRouter.

### 3. OpenRouter

HTTP API:

```text
GET https://openrouter.ai/api/v1/models?q={model}
```

Example:

```text
GET https://openrouter.ai/api/v1/models?q=gpt-4o
```

The resolver uses exact model id matching. OpenRouter ids include provider and
model:

```text
openai/gpt-4o
google/gemini-2.5-pro
anthropic/claude-sonnet-5
```

The resolver reads:

```json
{
  "pricing": {
    "prompt": "0.000005",
    "completion": "0.00003"
  }
}
```

OpenRouter prices are already USD per token.

## Alias And Provider Inference

Many Xparse rows use `provider = "vllm"` because the model is served by a
self-hosted OpenAI-compatible endpoint. The public price should still come from
the upstream model provider.

The alias layer wraps the resolver chain and retries known safe catalog
identities.

Provider inference:

```text
gpt-*             -> openai
o1/o3/o4*         -> openai
claude-*          -> anthropic
gemini-*          -> google
glm-*             -> z-ai
z-ai/*            -> z-ai
zai-org/*         -> z-ai
```

Specific model aliases added from live catalog probes:

```text
zai-org/GLM-5.2   -> z-ai / glm-5.2
claude-3-7-sonnet -> anthropic / claude-3-7-sonnet-latest
```

The alias layer is conservative:

- It may infer public-provider prices for generic hosts such as `vllm`.
- It does not reprice a concrete cloud provider as a different provider.
- Explicit request fields `pricing_provider` and `pricing_model` take priority
  over inference.

## Request Fields

The create-model request now supports optional pricing fields:

```json
{
  "provider": "vllm",
  "model_name": "gpt-5.5",
  "display_name": "gpt-5.5",
  "tier": "standard",
  "endpoint": "http://vllm.example/v1",
  "cost_per_input_token": null,
  "cost_per_output_token": null,
  "pricing_provider": "openai",
  "pricing_model": "gpt-5.5"
}
```

`pricing_provider` and `pricing_model` are request-scoped lookup overrides only.
They are not persisted to the `Model` table.

## Configuration

Default settings:

```text
XPARSE_MODEL_PRICING_RESOLVER=cascade
XPARSE_MODEL_PRICING_CHAIN=portkey,litellm,openrouter
XPARSE_MODEL_PRICING_BASE_URL=https://api.portkey.ai
XPARSE_OPENROUTER_MODEL_CATALOG_BASE_URL=https://openrouter.ai/api/v1
XPARSE_MODEL_PRICING_TIMEOUT_SECONDS=2.0
```

Supported resolver modes:

```text
XPARSE_MODEL_PRICING_RESOLVER=none
XPARSE_MODEL_PRICING_RESOLVER=portkey
XPARSE_MODEL_PRICING_RESOLVER=litellm
XPARSE_MODEL_PRICING_RESOLVER=openrouter
XPARSE_MODEL_PRICING_RESOLVER=cascade
XPARSE_MODEL_PRICING_RESOLVER=portkey,openrouter
```

`none`, `disabled`, or `off` disables automatic pricing lookup.

## Existing Rows And Backfill

Create-time lookup only affects newly created models. Existing rows that already
have `NULL` prices need a backfill.

Command:

```bash
cd /Users/peter/Desktop/X-parse/xparse/xparse_iam
.venv/bin/python manage.py backfill_model_pricing --dry-run --json
.venv/bin/python manage.py backfill_model_pricing
```

Optional filters:

```bash
.venv/bin/python manage.py backfill_model_pricing --group-uuid <group_uuid>
.venv/bin/python manage.py backfill_model_pricing --model-uuid <model_uuid>
.venv/bin/python manage.py backfill_model_pricing --include-inactive
```

Backfill behavior:

- only fills `NULL` price fields
- does not overwrite explicit `0.0` or non-null values
- updates `Model` rows
- updates active `ApplicationModel` bindings that still have `NULL` price fields
- runs each model update in `transaction.atomic()`
- re-reads updated rows and verifies post-conditions

## Live Probe Result

After alias/provider inference, these models resolve successfully:

```text
gpt-4o              input 2.5 $/M   output 10 $/M
gpt-5.4-mini        input 0.75 $/M  output 4.5 $/M
zai-org/GLM-5.2     input 0.93 $/M  output 3 $/M
claude-3-7-sonnet   input 3 $/M     output 15 $/M
gemini-2.5-pro      input 1.25 $/M  output 10 $/M
claude-sonnet-5     input 2 $/M     output 10 $/M
claude-opus-4-8     input 5 $/M     output 25 $/M
gpt-3.5-turbo       input 0.5 $/M   output 1.5 $/M
```

## Files Created

```text
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/application/use_cases/model/pricing.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/infrastructure/model_pricing/__init__.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/infrastructure/model_pricing/aliases.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/infrastructure/model_pricing/composite.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/infrastructure/model_pricing/discovery.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/infrastructure/model_pricing/factory.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/infrastructure/model_pricing/litellm.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/infrastructure/model_pricing/openrouter.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/infrastructure/model_pricing/portkey.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/management/commands/backfill_model_pricing.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/tests/unit/test_model_create_pricing.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/tests/unit/test_model_pricing.py
```

## Files Modified

```text
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/settings.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/application/use_cases/model/create_model.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/infrastructure/repositories/django/model_repository.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/api/schemas/_application.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/api/ninja_api/_models.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/xparse_iam/api/iam_crud_audit/_base.py
/Users/peter/Desktop/X-parse/xparse/tests/unit/audit_tests/test_iam_crud_audit.py
/Users/peter/Desktop/X-parse/xparse/xparse_iam/tests/conftest.py
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/types/iam.ts
/Users/peter/Desktop/X-parse/xparse/frontend/console-app-refactor/src/components/features/llm-proxy/models/create-model-dialog.tsx
```

## File-Level Change Summary

### Backend application layer

`xparse_iam/xparse_iam/application/use_cases/model/pricing.py`

- Added `ModelTokenPricing`.
- Added `ModelPricingResolver` protocol.
- Added lookup identity helpers:
  - `pricing_lookup_provider`
  - `pricing_lookup_model`
  - `pricing_lookup_model_name`

`xparse_iam/xparse_iam/application/use_cases/model/create_model.py`

- Added optional input fields:
  - `cost_per_input_token`
  - `cost_per_output_token`
  - `pricing_provider`
  - `pricing_model`
- Added `pricing_resolver` parameter to `create_model`.
- Added `_with_resolved_pricing`.
- Ensures explicit user-provided prices are not overwritten.

### Backend infrastructure layer

`xparse_iam/xparse_iam/infrastructure/model_pricing/portkey.py`

- Added Portkey pricing resolver.
- Calls `GET /model-configs/pricing/{provider}/{model}`.
- Converts Portkey cents/token to Xparse USD/token.
- Handles upstream HTTP and JSON failures as lookup misses.

`xparse_iam/xparse_iam/infrastructure/model_pricing/litellm.py`

- Added optional LiteLLM resolver.
- Uses `get_llm_provider` and `litellm.model_cost`.
- Does not require LiteLLM as a hard dependency.

`xparse_iam/xparse_iam/infrastructure/model_pricing/openrouter.py`

- Added OpenRouter resolver.
- Calls `GET /models?q={model}`.
- Reads `pricing.prompt` and `pricing.completion`.
- Uses exact OpenRouter model id matching.

`xparse_iam/xparse_iam/infrastructure/model_pricing/composite.py`

- Added resolver chain.
- Returns the first resolver result with at least one price field.

`xparse_iam/xparse_iam/infrastructure/model_pricing/aliases.py`

- Added provider inference and deterministic alias retry layer.
- Handles generic hosts such as `vllm`.
- Adds known aliases for GLM 5.2 and Claude 3.7 Sonnet.

`xparse_iam/xparse_iam/infrastructure/model_pricing/discovery.py`

- Added provider normalization.
- Added policy for when discovered provider pricing is acceptable.

`xparse_iam/xparse_iam/infrastructure/model_pricing/factory.py`

- Added configurable resolver factory.
- Supports single resolver, comma-separated resolver chains, and default
  `cascade`.
- Wraps resolver chain with alias inference.

`xparse_iam/xparse_iam/infrastructure/repositories/django/model_repository.py`

- Persists model pricing fields to `Model`.
- Copies model pricing to `ApplicationModel` when model creation also provisions
  a binding.

### API layer

`xparse_iam/xparse_iam/api/schemas/_application.py`

- Added create request fields:
  - `cost_per_input_token`
  - `cost_per_output_token`
  - `pricing_provider`
  - `pricing_model`
- Added response fields:
  - `cost_per_input_token`
  - `cost_per_output_token`

`xparse_iam/xparse_iam/api/ninja_api/_models.py`

- Injects `get_model_pricing_resolver()` into create-model use case.
- Passes pricing and pricing override fields from request schema.
- Returns pricing fields in model responses.

`xparse_iam/xparse_iam/api/iam_crud_audit/_base.py`

- Includes model pricing fields in model audit snapshots.

### Settings

`xparse_iam/xparse_iam/settings.py`

- Added model pricing resolver settings:
  - `XPARSE_MODEL_PRICING_RESOLVER`
  - `XPARSE_MODEL_PRICING_CHAIN`
  - `XPARSE_MODEL_PRICING_BASE_URL`
  - `XPARSE_OPENROUTER_MODEL_CATALOG_BASE_URL`
  - `XPARSE_MODEL_PRICING_TIMEOUT_SECONDS`

### Management command

`xparse_iam/xparse_iam/management/commands/backfill_model_pricing.py`

- Added dry-run capable pricing backfill command.
- Fills missing `Model` and active `ApplicationModel` prices.
- Keeps explicit operator values intact.
- Uses atomic writes and post-condition verification.

### Frontend

`frontend/console-app-refactor/src/types/iam.ts`

- Added pricing fields to `ModelCreateRequest`.
- Added pricing fields to `ModelResponse`.
- Added optional pricing override fields.

`frontend/console-app-refactor/src/components/features/llm-proxy/models/create-model-dialog.tsx`

- When a newly created model is bound to an LLM Proxy, the binding payload now
  copies the created model's resolved prices.

### Tests

`xparse_iam/tests/unit/test_model_pricing.py`

- Added tests for:
  - Portkey unit conversion
  - Portkey provider aliasing
  - LiteLLM resolver behavior
  - OpenRouter resolver behavior
  - composite resolver fallback order
  - alias/provider inference
  - ambiguous/mismatched provider handling

`xparse_iam/tests/unit/test_model_create_pricing.py`

- Added use-case tests for:
  - create-time automatic pricing enrichment
  - `served_model_name` lookup
  - `pricing_provider` / `pricing_model` overrides
  - preserving explicit pricing
  - resolver miss leaving pricing empty

`tests/unit/audit_tests/test_iam_crud_audit.py`

- Updated audit snapshot expectations to include pricing fields.

`xparse_iam/tests/conftest.py`

- Disables external pricing resolver during test setup by default:

```text
XPARSE_MODEL_PRICING_RESOLVER=none
```

## Verification Performed

Commands run:

```bash
python -m py_compile \
  xparse_iam/xparse_iam/application/use_cases/model/pricing.py \
  xparse_iam/xparse_iam/application/use_cases/model/create_model.py \
  xparse_iam/xparse_iam/infrastructure/model_pricing/*.py \
  xparse_iam/xparse_iam/management/commands/backfill_model_pricing.py
```

```bash
xparse_iam/.venv/bin/ruff check --select I,F,E501 \
  xparse_iam/xparse_iam/application/use_cases/model/pricing.py \
  xparse_iam/xparse_iam/application/use_cases/model/create_model.py \
  xparse_iam/xparse_iam/infrastructure/model_pricing \
  xparse_iam/xparse_iam/management/commands/backfill_model_pricing.py \
  xparse_iam/tests/unit/test_model_pricing.py \
  xparse_iam/tests/unit/test_model_create_pricing.py
```

```bash
cd /Users/peter/Desktop/X-parse/xparse/xparse_iam
.venv/bin/python -m pytest -o addopts= \
  tests/unit/test_model_pricing.py \
  tests/unit/test_model_create_pricing.py
```

Result:

```text
21 passed
```

Audit snapshot tests were also run earlier:

```bash
uv run pytest tests/unit/audit_tests/test_iam_crud_audit.py::TestModelSnapshots
```

Result:

```text
3 passed
```

Frontend validation was not run automatically, following the local guidance for
`frontend/console-app-refactor`.
