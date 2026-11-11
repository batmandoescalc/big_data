#!/usr/bin/env bash
# Count the day's distinct pages twice on the real cluster, through YARN, over
# the same HDFS input and with the same job settings:
#   fm     each mapper sends at most 4,096 register lines through the shuffle
#   exact  every page key goes through the shuffle
# Run on the controller from a checkout of this repository.  Both jobs write
# under a NEW HDFS output folder; the script refuses if it already exists and
# never deletes or overwrites anything in HDFS.  It changes no cluster
# configuration: the -D settings below apply to these two jobs only.
#
# Usage: run-distinct-cluster.sh /hdfs/input-dir /new/hdfs/output-dir [REDUCERS]
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 || "$1" != /* || "$2" != /* ]]; then
  echo "Usage: bash $0 /hdfs/input-dir /new/hdfs/output-dir [REDUCERS]" >&2
  exit 2
fi
input=${1%/}
output=${2%/}
reducers=${3:-3}
[[ "$reducers" =~ ^[1-9][0-9]*$ ]] || { echo "REDUCERS must be a whole number" >&2; exit 2; }

# shellcheck disable=SC1091
source /etc/profile.d/hadoop.sh
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
week7="$(cd -- "$script_dir/../../../week-07/scripts" && pwd)"
# Local results folder, ignored by Git.
results_dir="$script_dir/../../../runtime/week-08/$(basename "$output")"
[[ ! -e "$results_dir" ]] || { echo "Local results folder already exists: $results_dir" >&2; exit 1; }

if hdfs dfs -test -e "$output"; then
  echo "Refusing to overwrite existing HDFS output: $output" >&2
  exit 1
fi

# Small health check (read-only): three workers registered, input healthy.
nodes="$(timeout 60 yarn node -list -states RUNNING 2>&1)" || true
[[ "$nodes" =~ Total\ Nodes:[[:space:]]*3([^0-9]|$) ]] || {
  echo "Health check failed: expected 3 running YARN workers. Nothing was submitted." >&2
  exit 1
}
fsck="$(timeout 300 hdfs fsck "$input" 2>&1)" || true
[[ "$fsck" == *"is HEALTHY"* ]] || {
  echo "Health check failed: HDFS does not report $input as HEALTHY. Nothing was submitted." >&2
  exit 1
}
echo "Health check passed: 3 YARN workers running, HDFS input HEALTHY."

shopt -s nullglob
jars=("$HADOOP_HOME"/share/hadoop/tools/lib/hadoop-streaming-*.jar)
shopt -u nullglob
[[ ${#jars[@]} -eq 1 ]] || { echo "Expected one Hadoop Streaming JAR" >&2; exit 1; }

# -files links each script into the task folder from its own cache folder and
# Python resolves the link, so sibling modules need PYTHONPATH=. to import.
modules="$script_dir/../pageviews.py,$script_dir/../dgim_reduced_error.py,$script_dir/../dgim_study.py,$week7/streaming.py"
fm_files="$script_dir/fm_pageviews_mapper.py,$week7/hadoop/fm_reducer.py,$modules"
exact_files="$script_dir/exact_distinct_mapper.py,$script_dir/exact_distinct_reducer.py,$modules"

mkdir -p "$results_dir"
results="$results_dir/results.tsv"
printf 'job\treducers\twall_seconds\tmap_input_records\tmap_output_records\treduce_shuffle_bytes\treduce_input_records\tanswer\n' >"$results"

# Read one counter from the job summary Hadoop prints when a job ends.
counter() {
  awk -F= -v name="$1" '{ label = $1; sub(/^[[:space:]]+/, "", label) }
    label == name { value = $2 } END { print value }' "$2"
}

# run_job NAME FILES MAPPER REDUCER FINISH_SCRIPT
# Both jobs go through this one command, so their settings cannot differ:
# same reducer count, the cluster's own memory settings, no speculative tasks.
# Students can only write inside their own HDFS home, so YARN's staging
# folder is pointed there (issue #19).
run_job() {
  local name=$1 files=$2 mapper=$3 reducer=$4 finish=$5
  local log="$results_dir/$name-job.log" started seconds answer
  started=$(date +%s)
  hadoop jar "${jars[0]}" \
    -D mapreduce.framework.name=yarn \
    -D mapreduce.job.name="week08-distinct-$name" \
    -D yarn.app.mapreduce.am.staging-dir="/user/$USER/.staging" \
    -D mapreduce.job.reduces="$reducers" \
    -D mapreduce.map.speculative=false \
    -D mapreduce.reduce.speculative=false \
    -files "$files" \
    -input "$input/pageviews-*.gz" \
    -output "$output/$name" \
    -mapper "python3 $mapper" \
    -reducer "python3 $reducer" \
    -cmdenv PYTHONIOENCODING=utf-8 \
    -cmdenv PYTHONPATH=. 2>&1 | tee "$log"
  seconds=$(( $(date +%s) - started ))
  hdfs dfs -test -e "$output/$name/_SUCCESS"
  answer=$(hdfs dfs -cat "$output/$name/part-*" | python3 "$script_dir/$finish")
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$reducers" "$seconds" \
    "$(counter 'Map input records' "$log")" "$(counter 'Map output records' "$log")" \
    "$(counter 'Reduce shuffle bytes' "$log")" "$(counter 'Reduce input records' "$log")" \
    "$answer" >>"$results"
}

# One job after the other, never together: each attached "hadoop jar" client
# holds about 209 MB on the controller.
run_job fm "$fm_files" fm_pageviews_mapper.py fm_reducer.py fm_finish.py
run_job exact "$exact_files" exact_distinct_mapper.py exact_distinct_reducer.py exact_distinct_finish.py

echo
echo "Both jobs finished. Results: $results"
cat "$results"
echo "The job logs beside it name cluster machines: keep them out of Git."
