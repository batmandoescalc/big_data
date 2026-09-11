#!/usr/bin/env bash
# Run on the controller as hadoop, with this directory copied alongside the script.
set -euo pipefail
if [[ $# -ne 1 || "$1" != /* ]]; then
  echo "Usage: bash $0 /absolute/new/hdfs/output" >&2
  exit 2
fi
# shellcheck disable=SC1091
source /etc/profile.d/hadoop.sh
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
input=/datasets/apollo11/2026-09-11/text
output="$1"

# Hadoop also refuses an existing output directory; never delete old results.
if hdfs dfs -test -e "$output"; then
  echo "Output already exists: $output" >&2
  exit 1
fi
hdfs dfs -test -d "$input"
shopt -s nullglob
jars=("$HADOOP_HOME"/share/hadoop/tools/lib/hadoop-streaming-*.jar)
[[ ${#jars[@]} -eq 1 ]] || { echo 'Expected one Hadoop Streaming JAR.' >&2; exit 1; }

hadoop jar "${jars[0]}" \
  -D mapreduce.framework.name=yarn \
  -D mapreduce.job.name=apollo11-python-wordcount \
  -D mapreduce.job.reduces=1 \
  -files "$script_dir/mapper.py,$script_dir/reducer.py" \
  -input "$input" \
  -output "$output" \
  -mapper 'python3 mapper.py' \
  -reducer 'python3 reducer.py' \
  -cmdenv PYTHONIOENCODING=utf-8

hdfs dfs -test -e "$output/_SUCCESS"
printf 'Completed. Read results with: hdfs dfs -cat "%s/part-*"\n' "$output"
