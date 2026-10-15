Title: Gateway: /v1/chat/completions 422 key-resolution message can name the hidden bound model on a select_available=false application (ADR-138 INV-138-22; chat counterpart of #6065)

## Problem

PR #6071 (#6065) stops `/v1/embeddings` from naming the hidden bound model in its error answers. Its fix is adapter-local and does not cover chat. `gateway/worker_setup.py:1025-1029` wraps the `KeyResolver`'s message verbatim into the chat 422: `detail=f"Provider key resolution failed: {error}"`. The resolver's messages name the model:

- `production/key_resolver.py:216-224` -- `Model {provider}/{model_name} has no credential bound. ...` -- even when `model_uuid` is passed (chat passes it, `worker_setup.py:1023`);
- `:186-191` -- on the UUID path `Model model_uuid=<uuid> not bound to this API key.` (names the UUID);
- `:155-163` -- `N bound models share the name provider/model (model_uuid=.../credential_uuid=...)` on the name-keyed YAML rung.

On an application that hides its names (`select_available=false`) addressed by its application code or a default-request token, the client did not name the model and must not learn it (INV-138-22).

### Evidence

- Code path verified by reading on `origin/main` `cbb78f0bf`; not verified end-to-end.
- Embeddings counterpart, real route: PR #6071 tests (`tests/integration/test_embeddings_opaque_error_messages.py`) show all three messages reaching the client before that fix.

## Desired

1. On a hidden-name application addressed by `APPLICATION_CODE` / `DEFAULT_TOKEN`, the chat 422 names the application (`application <code>` / `this application`), never the model or any UUID; the full message goes to the gateway log with the request id.
2. Unchanged: visible applications, client-named models, status / type / code.

## Acceptance

- [ ] Real chat route, hidden-name app, bound model without a credential -> 422 body without the bound name or any UUID. Seen red on main first.
- [ ] Controls byte-identical: visible app, named model.

## Out of scope

- The resolver's audit seam (separate issue).
