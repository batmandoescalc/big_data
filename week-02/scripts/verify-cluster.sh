#!/usr/bin/env bash
# Run as the Hadoop service account on the controller after all nodes are ready.
set -euo pipefail
# shellcheck disable=SC1091
source /etc/profile.d/hadoop.sh

report="$(timeout 30 hdfs dfsadmin -report)"
printf '%s\n' "$report"
[[ "$report" =~ Live\ datanodes\ \(3\) ]] || { echo 'Expected three live HDFS workers.' >&2; exit 1; }
nodes="$(timeout 30 yarn node -list -states RUNNING)"
printf '%s\n' "$nodes"
[[ "$nodes" =~ Total\ Nodes:[[:space:]]*3([^0-9]|$) ]] || { echo 'Expected three running YARN workers.' >&2; exit 1; }
timeout 90 hdfs dfsadmin -safemode wait

verify_tmp="$(mktemp -d /tmp/hadoop-verify.XXXXXXXX)"
trap 'rm -rf -- "$verify_tmp"' EXIT
run="/tmp/poc/verify-$(date -u +%Y%m%dT%H%M%SZ)-${verify_tmp##*.}"
for n in 1 2 3; do
  printf 'cat dog cat\n' >"$verify_tmp/input-$n.txt"
done
timeout 30 hdfs dfs -mkdir -p "$run/input"
timeout 60 hdfs dfs -put "$verify_tmp"/input-*.txt "$run/input/"
timeout 180 hdfs dfs -setrep -w 2 "$run/input"
timeout 30 hdfs dfs -cat "$run/input/input-1.txt" >"$verify_tmp/readback.txt"
cmp "$verify_tmp/input-1.txt" "$verify_tmp/readback.txt"

shopt -s nullglob
jars=("$HADOOP_HOME"/share/hadoop/mapreduce/hadoop-mapreduce-examples-*.jar)
[[ ${#jars[@]} -eq 1 ]] || { echo 'Expected exactly one Hadoop examples JAR.' >&2; exit 1; }
timeout 300 hadoop jar "${jars[0]}" wordcount "$run/input" "$run/output"
timeout 30 hdfs dfs -cat "$run/output/part-r-*" | LC_ALL=C sort >"$verify_tmp/result.txt"
printf 'cat\t6\ndog\t3\n' >"$verify_tmp/expected.txt"
diff -u "$verify_tmp/expected.txt" "$verify_tmp/result.txt"
timeout 30 hdfs fsck "$run" -files -blocks -locations
printf 'PASS: three HDFS workers, three YARN workers, replicated file readback, and MapReduce word count. Results: %s\n' "$run"
