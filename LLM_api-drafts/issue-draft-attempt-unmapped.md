Title: Gateway (coordinated): /v1/embeddings on an application whose embedding model is its IAM profile is always refused 503 attempt_unmapped

## Problem

On a coordinated gateway (`shared_admission` set; prod is single-active today, so latent), every `/v1/embeddings` call goes through `attempt_scope` (`gateway/unary_execution.py:229`). The call is named by `CredentialNames.name` (`production/coordination/metering.py:56-80`): with no `model_uuid` (opaque requests pass `slot.budget_model_uuid`, which is `None`), it looks up `(provider, model_name)` in `by_name`, built only from `auth_context.models` (`:83-106`). An application whose embedding model is its ADR-089 IAM embedding profile (`embedding_profile_config`), not a bound catalog model, has no such entry -> `AttemptUnmapped("no single model bound to this key is named vllm/<name>")` -> 503 `attempt_unmapped`, for every application, visible or not. The provider is never called.

### Evidence

- PR #6071's first revision exercised it on the real route (conformance harness: IAM profile `vllm/embed-conformance`, `_CoordinationAuthority(refuse=None)`): 503 `attempt on model None refused: no single model bound to this key is named vllm/embed-conformance` for `select_available` true and false (`git show 7157c3b49:apps/gateway/bustream/tests/integration/test_embeddings_opaque_error_messages.py`, the per-attempt test).
- Not investigated further: whether an IAM-profile embedding is meant to be metered per attempt, and by which identity.

### Why it matters

- If a gateway is ever run coordinated, IAM-profile embeddings stop working entirely, with a retryable-looking 503.

## Desired

Decide (ADR-494 / SPEC-289 owner) how an IAM-profile embedding attempt is named for the per-attempt check -- e.g. by the profile's credential -- or that it is not metered per attempt; then make the call succeed or refuse with a non-retryable, documented answer.

## Acceptance

- [ ] Real route on a coordinated gateway with an IAM embedding profile: the call reaches the provider (or is refused as decided), seen red on main first.

## Related

- Side observation from the same work: on an opaque request admission budgets `ctx.input.request.model` (the application code), so `budget_model_uuid` is `None` and the executed model's fleet-wide ceiling is not looked up. Not verified end-to-end.
