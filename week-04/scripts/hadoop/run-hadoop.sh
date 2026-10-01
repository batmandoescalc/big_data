#!/usr/bin/env bash
# Run on the controller as hadoop, with lsh.py and this directory's scripts
# copied alongside. Never overwrites HDFS input or output.
set -euo pipefail
if [[ $# -ne 4 || "$1" != /* || "$2" != /* ]]; then
  echo "Usage: bash $0 /hdfs/signatures.tsv /new/hdfs/output-base BANDS ROWS" >&2
  exit 2
fi
input=$1
base=$2
bands=$3
rows=$4
[[ "$bands" =~ ^[0-9]+$ && "$rows" =~ ^[0-9]+$ ]] || { echo "BANDS and ROWS must be integers" >&2; exit 2; }
# shellcheck disable=SC1091
source /etc/profile.d/hadoop.sh
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
buckets="$base/candidate-pairs"
pairs="$base/deduped-pairs"

for path in "$buckets" "$pairs"; do
  if hdfs dfs -test -e "$path"; then
    echo "Output already exists: $path" >&2
    exit 1
  fi
done
hdfs dfs -test -f "$input"
shopt -s nullglob
jars=("$HADOOP_HOME"/share/hadoop/tools/lib/hadoop-streaming-*.jar)
[[ ${#jars[@]} -eq 1 ]] || { echo 'Expected one Hadoop Streaming JAR.' >&2; exit 1; }

# Print elapsed seconds for one labeled step, using a monotonic-enough ns clock.
timed() {
  local label=$1; shift
  local start end
  start=$(date +%s%N)
  "$@"
  end=$(date +%s%N)
  printf 'TIMING %s %d.%03d s\n' "$label" $(((end - start) / 1000000000)) $((((end - start) / 1000000) % 1000))
}

total_start=$(date +%s%N)
timed lsh-banding-job hadoop jar "${jars[0]}" \
  -D mapreduce.framework.name=yarn \
  -D mapreduce.job.name=apollo11-lsh-banding \
  -D mapreduce.job.reduces=3 \
  -files "$script_dir/lsh.py,$script_dir/lsh_mapper.py,$script_dir/lsh_reducer.py" \
  -input "$input" \
  -output "$buckets" \
  -mapper "python3 lsh_mapper.py $bands $rows" \
  -reducer 'python3 lsh_reducer.py' \
  -cmdenv PYTHONIOENCODING=utf-8
hdfs dfs -test -e "$buckets/_SUCCESS"

# Pairs found in several bands, or by several reducers, collapse here. The key
# is both IDs (two fields), so identical pairs are grouped next to each other;
# with the default one-field key, copies of a pair could arrive apart.
timed dedupe-job hadoop jar "${jars[0]}" \
  -D mapreduce.framework.name=yarn \
  -D mapreduce.job.name=apollo11-lsh-dedupe \
  -D stream.num.map.output.key.fields=2 \
  -D mapreduce.job.reduces=1 \
  -files "$script_dir/dedupe_reducer.py" \
  -input "$buckets/part-*" \
  -output "$pairs" \
  -mapper cat \
  -reducer 'python3 dedupe_reducer.py' \
  -cmdenv PYTHONIOENCODING=utf-8
hdfs dfs -test -e "$pairs/_SUCCESS"
total_end=$(date +%s%N)
printf 'TIMING hadoop-total %d.%03d s\n' $(((total_end - total_start) / 1000000000)) $((((total_end - total_start) / 1000000) % 1000))
echo "Raw bucket pairs: $(hdfs dfs -cat "$buckets/part-*" | wc -l)"
echo "Deduplicated pairs: $(hdfs dfs -cat "$pairs/part-*" | wc -l)"
