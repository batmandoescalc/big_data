#!/usr/bin/env bash
# Run on the controller as hadoop. Never overwrites HDFS input or output.
set -euo pipefail

if [[ $# -ne 5 ]]; then
  echo "Usage: bash $0 INPUT_DIR OUTPUT_BASE UTTERANCE_ROWS MATCHED_ROWS AGGREGATE_ROWS" >&2
  exit 2
fi
input=$1
output_base=$2
utterance_rows=$3
matched_rows=$4
aggregate_rows=$5
[[ "$input" == /* && "$output_base" == /* ]] || {
  echo "HDFS paths must be absolute" >&2
  exit 2
}
[[ "$utterance_rows" =~ ^[0-9]+$ && "$matched_rows" =~ ^[0-9]+$ && "$aggregate_rows" =~ ^[0-9]+$ ]] || {
  echo "Row counts must be nonnegative integers" >&2
  exit 2
}

# shellcheck disable=SC1091
source /etc/profile.d/hadoop.sh
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
week_dir="$(cd -- "$script_dir/../.." && pwd)"
joined="$output_base/joined"
aggregated="$output_base/aggregates"
runtime_dir="$week_dir/runtime/$(basename "$output_base")"
mkdir -p "$runtime_dir"

for path in "$joined" "$aggregated"; do
  if hdfs dfs -test -e "$path"; then
    echo "Output already exists: $path" >&2
    exit 1
  fi
done
hdfs dfs -test -f "$input/utterances.tsv"
hdfs dfs -test -f "$input/speakers.tsv"
actual_utterances=$(hdfs dfs -cat "$input/utterances.tsv" | awk 'NR > 1' | wc -l)
speaker_rows=$(hdfs dfs -cat "$input/speakers.tsv" | awk 'NR > 1' | wc -l)
[[ "$actual_utterances" -eq "$utterance_rows" ]] || {
  echo "Unexpected utterance row count: $actual_utterances" >&2
  exit 1
}
input_rows=$((actual_utterances + speaker_rows))
shopt -s nullglob
jars=("$HADOOP_HOME"/share/hadoop/tools/lib/hadoop-streaming-*.jar)
[[ ${#jars[@]} -eq 1 ]] || { echo "Expected one Hadoop Streaming JAR" >&2; exit 1; }

pipeline_started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
pipeline_start_ns=$(date +%s%N)

python3 "$week_dir/scripts/run_timed.py" \
  --label hadoop-join \
  --engine hadoop-streaming \
  --dataset-id apollo11-week03 \
  --manifest "$runtime_dir/hadoop-join.json" \
  --input-rows "$input_rows" \
  --output-rows "$matched_rows" -- \
  hadoop jar "${jars[0]}" \
    -D mapreduce.framework.name=yarn \
    -D mapreduce.job.name=apollo11-speaker-natural-join \
    -D mapreduce.job.reduces=1 \
    -files "$script_dir/join_mapper.py,$script_dir/join_reducer.py" \
    -input "$input/utterances.tsv" \
    -input "$input/speakers.tsv" \
    -output "$joined" \
    -mapper "python3 join_mapper.py" \
    -reducer "python3 join_reducer.py" \
    -cmdenv PYTHONIOENCODING=utf-8

hdfs dfs -test -e "$joined/_SUCCESS"

python3 "$week_dir/scripts/run_timed.py" \
  --label hadoop-grouping-aggregation \
  --engine hadoop-streaming \
  --dataset-id apollo11-week03 \
  --manifest "$runtime_dir/hadoop-aggregation.json" \
  --input-rows "$matched_rows" \
  --output-rows "$aggregate_rows" -- \
  hadoop jar "${jars[0]}" \
    -D mapreduce.framework.name=yarn \
    -D mapreduce.job.name=apollo11-speaker-grouping-aggregation \
    -D mapreduce.job.reduces=1 \
    -files "$script_dir/aggregate_mapper.py,$script_dir/aggregate_reducer.py" \
    -input "$joined/part-*" \
    -output "$aggregated" \
    -mapper "python3 aggregate_mapper.py" \
    -reducer "python3 aggregate_reducer.py" \
    -cmdenv PYTHONIOENCODING=utf-8

hdfs dfs -test -e "$aggregated/_SUCCESS"
actual_joined=$(hdfs dfs -cat "$joined/part-*" | wc -l)
actual_aggregates=$(hdfs dfs -cat "$aggregated/part-*" | wc -l)
[[ "$actual_joined" -eq "$matched_rows" ]]
[[ "$actual_aggregates" -eq "$aggregate_rows" ]]

pipeline_end_ns=$(date +%s%N)
python3 - "$runtime_dir/hadoop-pipeline.json" "$pipeline_started" \
  "$pipeline_start_ns" "$pipeline_end_ns" "$input_rows" \
  "$actual_joined" "$actual_aggregates" <<'PY'
import json
from pathlib import Path
import sys

path, started, start_ns, end_ns, inputs, joined, aggregates = sys.argv[1:]
record = {
    "label": "hadoop-full-pipeline",
    "started_utc": started,
    "elapsed_seconds": round((int(end_ns) - int(start_ns)) / 1_000_000_000, 6),
    "exit_status": 0,
    "input_rows": int(inputs),
    "joined_rows": int(joined),
    "aggregate_rows": int(aggregates),
}
Path(path).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
PY

echo "Completed Week 3 Hadoop pipeline"
echo "Joined output: $joined"
echo "Aggregate output: $aggregated"
hdfs dfs -cat "$aggregated/part-*"
