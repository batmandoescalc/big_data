#!/usr/bin/env bash
# Read-only safety checks required before staging large Week 5 inputs.
set -euo pipefail

required_logical_bytes=${1:-128849018880} # 120 GiB, all nested samples plus margin
[[ "$required_logical_bytes" =~ ^[0-9]+$ ]] || {
  echo "Required logical bytes must be an integer" >&2
  exit 2
}

# shellcheck disable=SC1091
source /etc/profile.d/hadoop.sh
temporary=$(mktemp -d)
trap 'rm -rf -- "$temporary"' EXIT

hdfs dfsadmin -report >"$temporary/hdfs-report.txt"
yarn node -list >"$temporary/yarn-nodes.txt" 2>&1
hdfs fsck / >"$temporary/fsck.txt" 2>&1
hdfs dfs -df / >"$temporary/df.txt"

live_datanodes=$(awk '/^Live datanodes \(/ {gsub(/[^0-9]/, "", $3); print $3; exit}' "$temporary/hdfs-report.txt")
yarn_nodes=$(awk -F: '/Total Nodes:/ {gsub(/[[:space:]]/, "", $2); print $2; exit}' "$temporary/yarn-nodes.txt")
available_bytes=$(awk 'NR > 1 && $2 ~ /^[0-9]+$/ {value=$4} END {print value}' "$temporary/df.txt")
replication=$(hdfs getconf -confKey dfs.replication)

[[ "$live_datanodes" == "3" ]] || { echo "Expected 3 live HDFS workers, found ${live_datanodes:-unknown}" >&2; exit 1; }
[[ "$yarn_nodes" == "3" ]] || { echo "Expected 3 YARN workers, found ${yarn_nodes:-unknown}" >&2; exit 1; }
grep -q 'is HEALTHY' "$temporary/fsck.txt" || {
  echo "HDFS is not healthy; inspect fsck before continuing" >&2
  exit 1
}
[[ "$replication" == "2" ]] || { echo "Expected dfs.replication=2, found $replication" >&2; exit 1; }

# Require 25% headroom above two physical replicas of the logical input.
required_physical_with_headroom=$((required_logical_bytes * 2 * 125 / 100))
[[ -n "$available_bytes" && "$available_bytes" -ge "$required_physical_with_headroom" ]] || {
  echo "Insufficient HDFS capacity: need $required_physical_with_headroom, available ${available_bytes:-unknown}" >&2
  exit 1
}

echo "PREFLIGHT OK"
echo "live_hdfs_workers=$live_datanodes"
echo "live_yarn_workers=$yarn_nodes"
echo "replication=$replication"
echo "available_hdfs_bytes=$available_bytes"
echo "required_with_headroom_bytes=$required_physical_with_headroom"
