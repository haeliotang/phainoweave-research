# Refusal audit end-to-end: CLI writer → append-only store → read-only cockpit

**Status:** demonstrated locally · 2026-11-06 · **Code:** `crates/phaino-core/src/actions.rs`, `crates/phaino-store/src/store.rs`, `crates/phaino-cli/src/main.rs` · **View:** `apps/desktop`

This is a synthetic governance exercise, not an E1 experiment. It verifies that a refused authorization leaves a durable audit row that the read-only cockpit can display.

## 1. Write a refusal

```
cargo run -q -p phaino-cli -- audit-check \
  --store .repro/audit-demo \
  --actor researcher-1 --authority researcher --action publish-evidence \
  --snapshot 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

Output (exit 2):

```
decision: Denied
reason: insufficient_authority
policy_digest: 659c438a…
input_snapshot_digest: 0123456789abcdef…
refusal audit row persisted
```

## 2. Store state

```
sequence  decision  actor          reason_code
1         denied    researcher-1   insufficient_authority
```

The store assigns the durable sequence; the core sequence is process-local. A second allowed attempt receives sequence 2:

```
cargo run -q -p phaino-cli -- audit-check \
  --store .repro/audit-demo \
  --actor publisher-1 --authority publisher --action publish-evidence
# decision: Allowed, exit 0
```

## 3. Inspect it without a GUI

```
cargo run -q -p phaino-cli -- audit-list --store .repro/audit-demo
cargo run -q -p phaino-cli -- audit-list --store .repro/audit-demo --json true
```

`audit-list` opens the store, prints persisted rows in sequence order, and makes no new audit entry. `audit-verify` verifies the store append-log chain, recomputes every audit payload digest and checks contiguous sequences:

```
cargo run -q -p phaino-cli -- audit-verify --store .repro/audit-demo
# audit chain verified
```

## 4. Read it in the cockpit

The Tauri host command `load_audit_events` opens the store with read-only flags, queries `audit_event`, and reports:

```
connected: true
rows: 2
```

The Governance view displays the rows when `PHAINOWEAVE_STORE` points at this store; the browser fallback reports `no store connected` rather than inventing rows. A unit test asserts the store file SHA-256 is unchanged by the read.

## 5. Limits

- Actors here are configured identities, not authenticated users; authentication remains outside this demo.
- The audit row can pin an input snapshot digest (`--snapshot`), but this synthetic command references a placeholder; it does not read the snapshot bytes.
- This is not an E1 result and does not authorize collection.
