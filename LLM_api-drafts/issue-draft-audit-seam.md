Title: Gateway: KeyResolver credential_resolved / credential_resolution_failed events never reach a running gateway's audit trail -- `_audit_emit` is the `bustream.audit.emit` module, not the function

## Problem

`production/key_resolver.py:19` binds its audit seam with `from bustream.audit import emit as _audit_emit`. `bustream/audit/__init__.py:48` defines a lazy `emit()` function, but importing the submodule `bustream.audit.emit` (which the package's own lazy `__getattr__`, `:92`, does on the first `AuditEmitter`/`set_emitter` access, e.g. `gateway/app.py:54`) rebinds the package attribute `emit` to the submodule. In a running gateway the resolver is imported after that, so `_audit_emit` is a module; `emit_audit()` (`key_resolver.py:70-74`) calls it, gets `TypeError: 'module' object is not callable`, and the fail-open `except Exception: pass` swallows it.

### Evidence

Re-verified on `origin/main` `cbb78f0bf` (paths under `apps/gateway/bustream/`):

```
$ PYTHONPATH=$PWD bustream/.venv/bin/python -c "import bustream.gateway.app; import bustream.production.key_resolver as k; print(type(k._audit_emit)); k._audit_emit(None, {})"
<class 'module'>
TypeError: 'module' object is not callable
```

- Only importer of this form outside tests: `production/key_resolver.py:19`.
- Even when called (unit tests patch the seam), the events carry no request/trace id -- the frozen `HttpAuthContext` has neither -- so the evidence bridge rejects them (`Mapping error: trace_id must be a non-empty string`, seen while writing PR #6071's tests).
- #702 fixed the identity fields of these events, not the seam.

### Why it matters

- Every `credential_resolved` / `credential_resolution_failed` event (all surfaces) is lost; a failed key resolution leaves only the gateway log.
- PR #6071 (#6065) relies on the log for the 422 detail and documents this in SPEC-308 UA-9.

## Desired

1. `key_resolver` calls the function, not whatever the package attribute is at import time (e.g. `from bustream.audit.emit import emit as _audit_emit`, or call through `bustream.audit.emit.emit` at call time).
2. The credential events carry the request's `request_id` / `trace_id` so the evidence bridge persists them.

## Acceptance

- [ ] Real-gateway test: import `bustream.gateway.app`, resolve a key with no credential, read the persisted trail -> one `credential_resolution_failed` with request and trace id. Seen red on main first.
- [ ] Static gate or test: `key_resolver._audit_emit` is callable after `bustream.gateway.app` is imported.

## Out of scope

- The wording of the resolver's messages (#6065 / PR #6071 handles what the embeddings client sees).
