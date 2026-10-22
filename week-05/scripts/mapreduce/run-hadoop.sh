#!/usr/bin/env bash
# Run the generic map-side join and aggregation on the existing YARN cluster.
set -euo pipefail

if [[ $# -ne 7 ]]; then
  echo "Usage: bash $0 FACTS DIMENSIONS OUTPUT DATASET_ID INPUT_ROWS INPUT_BYTES OUTPUT_ROWS" >&2
  exit 2
fi
facts=$1
dimensions=$2
output=$3
dataset_id=$4
input_rows=$5
input_bytes=$6
output_rows=$7
[[ "$facts" == /* && "$dimensions" == /* && "$output" == /* ]] || {
  echo "HDFS paths must be absolute" >&2
  exit 2
}
for value in "$input_rows" "$input_bytes" "$output_rows"; do
  [[ "$value" =~ ^[0-9]+$ ]] || { echo "counts and bytes must be integers" >&2; exit 2; }
done

# shellcheck disable=SC1091
source /etc/profile.d/hadoop.sh
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
week_dir="$(cd -- "$script_dir/../.." && pwd)"
repo_root="$(cd -- "$week_dir/.." && pwd)"
runtime_root="${WEEK05_RUNTIME_ROOT:-$week_dir/runtime}"
runtime_dir="$runtime_root/$(basename "$output")"
mkdir -p "$runtime_dir"

hdfs dfs -test -f "$facts"
hdfs dfs -test -f "$dimensions"
if hdfs dfs -test -e "$output"; then
  echo "Output already exists: $output" >&2
  exit 1
fi
shopt -s nullglob
jars=("$HADOOP_HOME"/share/hadoop/tools/lib/hadoop-streaming-*.jar)
[[ ${#jars[@]} -eq 1 ]] || { echo "Expected one Hadoop Streaming JAR" >&2; exit 1; }
default_fs=$(hdfs getconf -confKey fs.defaultFS)
dimension_uri="${default_fs%/}${dimensions}#namespaces.tsv"

python3 "$repo_root/common/benchmark/run_timed.py" \
  --label map-side-join-aggregation \
  --engine hadoop-streaming \
  --dataset-id "$dataset_id" \
  --manifest "$runtime_dir/hadoop.json" \
  --input-rows "$input_rows" \
  --input-bytes "$input_bytes" \
  --output-rows "$output_rows" -- \
  hadoop jar "${jars[0]}" \
    -D mapreduce.framework.name=yarn \
    -D mapreduce.job.name="week05-${dataset_id}" \
    -D mapreduce.job.reduces=1 \
    -files "$dimension_uri,$script_dir/map_join_aggregate.py,$script_dir/aggregate_reducer.py" \
    -input "$facts" \
    -output "$output" \
    -mapper "python3 map_join_aggregate.py namespaces.tsv" \
    -combiner "python3 aggregate_reducer.py" \
    -reducer "python3 aggregate_reducer.py" \
    -cmdenv PYTHONIOENCODING=utf-8

hdfs dfs -test -e "$output/_SUCCESS"
actual_rows=$(hdfs dfs -cat "$output/part-*" | wc -l)
[[ "$actual_rows" -eq "$output_rows" ]] || {
  echo "Unexpected output row count: $actual_rows" >&2
  exit 1
}
hdfs dfs -cat "$output/part-*"
