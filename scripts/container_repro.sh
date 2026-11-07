#!/usr/bin/env bash
# Run the test suite and E0 replay in a fixed Linux container and compare the
# E0 digest with the host's recorded golden digest.
#
# Usage: scripts/container_repro.sh [--platform linux/arm64|linux/amd64]
#
# The repository is copied to a temporary directory first, so container writes
# (target/, artifacts/) do not touch the working tree and uncommitted files are
# included. Network is used only for cargo fetch and (if missing) the image.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
platform="${PLATFORM:-linux/arm64}"
if [[ "${1:-}" == "--platform" ]]; then
  platform="${2:?--platform needs a value}"
fi
image="${IMAGE:-phainoweave-repro:1.94-py311}"
out_dir="${OUT_DIR:-$repo_root/.repro/container-${platform//\//-}}"
mkdir -p "$out_dir"

echo "=== build image ($image) ==="
docker build --platform "$platform" -t "$image" "$repo_root/containers/repro" | tee "$out_dir/build.log"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
echo "=== copy tree to $work/repo (excluding build outputs) ==="
rsync -a \
  --exclude '.git' --exclude 'target' --exclude 'artifacts' \
  --exclude 'node_modules' --exclude '.repro' --exclude 'dist' \
  "$repo_root/" "$work/repo/"

echo "=== container: cargo fetch + make test + make e0 ==="
set +e
# Keep the E0 failure as data: a digest mismatch is an R1-D result, not an
# infrastructure error. Test failures still fail the script because no run
# record is produced and the extraction below reports "missing".
docker run --rm --platform "$platform" \
  -v "$work/repo:/work" -w /work \
  "$image" bash -c "cargo fetch && make test && (make e0 || echo \$? > /work/.e0-status)" \
  >"$out_dir/run.log" 2>&1
status=$?
set -e
tail -40 "$out_dir/run.log"

if [[ $status -ne 0 ]]; then
  echo "container test run failed before E0; see $out_dir/run.log" >&2
  exit $status
fi

observed="$(python3 - "$work/repo" <<'PY'
import glob, json, sys
paths = glob.glob(sys.argv[1] + "/artifacts/e0-fabric/runs/*.json")
if not paths:
    print("missing")
else:
    print(json.load(open(paths[0])).get("observed_digest", "missing"))
PY
)"
expected="674213d9737f999a84aa8b57cddd9078e0bf2b2998ae02a45d0940cd98185506"
{
  echo "platform: $platform"
  echo "image: $image"
  echo "container_exit: $status"
  echo "host_expected_digest: $expected"
  echo "container_observed_digest: $observed"
  echo "container_e0_exit: $(cat "$work/repo/.e0-status" 2>/dev/null || echo 0)"
echo "exact_match: $([[ "$observed" == "$expected" ]] && echo true || echo false)"
} | tee "$out_dir/summary.txt"

if [[ "$observed" == "$expected" ]]; then
  exit 0
fi
if [[ "${ALLOW_MISMATCH:-0}" == "1" ]]; then
  echo "R1-D mismatch recorded as negative evidence (ALLOW_MISMATCH=1); see $out_dir/summary.txt"
  exit 0
fi
echo "R1-D strict byte equality failed; set ALLOW_MISMATCH=1 to keep the evidence and exit 0" >&2
exit 1
