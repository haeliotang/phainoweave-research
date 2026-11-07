# E1-0 filesystem sandbox — containerized execution boundary

**Status:** implemented and exercised locally on Linux-container E0 · 2026-11-07 · **Script:** `scripts/sandboxed_e0.sh` · **Gate:** [E1-0 raw bundle](E1-0-raw-bundle-schema.md)

This is an **OS-level boundary for running the E0/E1 Python analysis**, not a claim that the host process itself is sandboxed.

## 1. What the boundary enforces

`scripts/sandboxed_e0.sh` runs the analysis inside a Docker container with:

- `--network none`;
- read-only container root (`--read-only`);
- repository mounted **read-only** at `/repo`;
- only the caller-selected output directory mounted writable at `/out`;
- tmpfs for `/tmp`, `HOME`, and cache;
- `--cap-drop ALL`, `no-new-privileges`;
- non-root host uid/gid;
- 4 GiB memory, 2 CPUs, 256 PID limit.

The Python process therefore cannot write into the repository or arbitrary host paths, cannot use the network, and cannot retain capabilities. It can read the repository and write only `/out` and tmpfs.

## 2. Verified run

```
scripts/sandboxed_e0.sh \
  --config artifacts/e0-fabric/blobs/sha256/fb/6e/<config> \
  --out .repro/sandboxed-e0
```

Result: `records_sha256 b77716f0…`, the known Linux-arm64 result; output is written only under `.repro/sandboxed-e0/`.

## 3. Honest limits

- The host `sandbox-exec` is unavailable in this environment (`sandbox_apply: Operation not permitted`); this script therefore uses the Linux-container boundary. It does not sandbox the macOS host itself.
- It requires Docker and the `phainoweave-repro` image. Base-image tags are mutable; image digests are not yet pinned.
- It is an explicit harness, not the default `phaino replay e0` path; the default CLI still runs Python on the host with resource/environment budgets, not OS filesystem isolation.
- Docker/container security is not equivalent to a signed, audited sandbox; the container runtime is part of the trusted computing base.
- This does not make an E1 bundle authentic; it only bounds side effects of the analysis process.
