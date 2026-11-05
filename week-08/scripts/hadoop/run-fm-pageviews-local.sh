#!/usr/bin/env bash
# Run the pageviews FM job with Hadoop Streaming in local mode: input and
# output on the head node's own disk (file://), one JVM, map tasks one at a
# time.  Used because students cannot write to HDFS yet (issue #19).  It
# changes no cluster configuration and refuses to overwrite earlier output.
#
# Usage: run-fm-pageviews-local.sh INPUT_DIR OUTPUT_DIR [REGISTER_BITS]
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 INPUT_DIR OUTPUT_DIR [REGISTER_BITS]" >&2
  exit 2
fi

input=$(cd "$1" && pwd)
output=$2
bits=${3:-12}
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
week7="$script_dir/../../../week-07/scripts"

if [[ -e "$output" ]]; then
  echo "Refusing to overwrite existing output: $output" >&2
  exit 1
fi
output=$(cd "$(dirname "$output")" && pwd)/$(basename "$output")
# Local mode needs scratch folders of its own; keep them beside the output in
# the student's home folder and remove them afterwards.
work="${output}.work"
mkdir -p "$work"
trap 'rm -rf "$work"' EXIT

# Small client heap: the job only holds one hour's register array at a time.
export HADOOP_CLIENT_OPTS="${HADOOP_CLIENT_OPTS:--Xmx512m}"

nice -n 19 hadoop jar "$HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming"*.jar \
  -D mapreduce.framework.name=local \
  -D fs.defaultFS=file:/// \
  -D hadoop.tmp.dir="$work" \
  -D mapreduce.cluster.local.dir="$work/local" \
  -D yarn.app.mapreduce.am.staging-dir="$work/staging" \
  -D mapreduce.job.reduces=1 \
  -files "$script_dir/fm_pageviews_mapper.py,$week7/hadoop/fm_reducer.py,$script_dir/../pageviews.py,$script_dir/../dgim_reduced_error.py,$script_dir/../dgim_study.py,$week7/streaming.py" \
  -mapper "python3 fm_pageviews_mapper.py $bits" \
  -reducer "python3 fm_reducer.py" \
  -input "file://$input/pageviews-*.gz" \
  -output "file://$output"

python3 "$script_dir/fm_finish.py" "$bits" < "$output/part-00000"
