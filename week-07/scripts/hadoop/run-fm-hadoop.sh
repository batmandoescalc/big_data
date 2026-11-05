#!/usr/bin/env bash
# Run a bounded Flajolet-Martin batch using Hadoop Streaming.  The caller must
# choose a new output path; this script refuses to overwrite prior evidence.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: $0 HDFS_INPUT HDFS_OUTPUT REGISTER_COUNT" >&2
  exit 2
fi

input=$1
output=$2
registers=$3
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
staging_args=()

# Student HDFS homes can keep YARN staging private even when the cluster's
# shared /tmp staging root is not student-writable. Service-account workflows
# may leave this unset and retain the cluster default.
if [[ -n "${HDFS_STAGING_DIR:-}" ]]; then
  [[ "$HDFS_STAGING_DIR" == /* ]] || {
    echo "HDFS_STAGING_DIR must be an absolute HDFS path." >&2
    exit 2
  }
  staging_args=(-D "yarn.app.mapreduce.am.staging-dir=$HDFS_STAGING_DIR")
fi

if hdfs dfs -test -e "$output"; then
  echo "Refusing to overwrite existing HDFS output: $output" >&2
  exit 1
fi

hadoop jar "$HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming"*.jar \
  "${staging_args[@]}" \
  -D mapreduce.job.reduces=1 \
  -files "$script_dir/fm_mapper.py,$script_dir/fm_reducer.py,$script_dir/../streaming.py" \
  -mapper "python3 fm_mapper.py $registers" \
  -reducer "python3 fm_reducer.py" \
  -input "$input" \
  -output "$output"
