#!/usr/bin/env bash
# Stage immutable samples and run three SQLite/Hadoop attempts per eligible size.
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "Usage: bash $0 LOCAL_SAMPLE_ROOT HDFS_INPUT_ROOT HDFS_OUTPUT_ROOT LOCAL_RUNTIME_ROOT" >&2
  exit 2
fi
local_root=$1
hdfs_input_root=$2
hdfs_output_root=$3
runtime_root=$4
[[ "$hdfs_input_root" == /* && "$hdfs_output_root" == /* ]] || {
  echo "HDFS roots must be absolute" >&2
  exit 2
}

# shellcheck disable=SC1091
source /etc/profile.d/hadoop.sh
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
week_dir="$(cd -- "$script_dir/.." && pwd)"
repo_root="$(cd -- "$week_dir/.." && pwd)"
[[ ! -e "$runtime_root" ]] || { echo "Immutable runtime root already exists: $runtime_root" >&2; exit 1; }
mkdir -p "$runtime_root"

"$script_dir/preflight-cluster.sh"

for sample in "$local_root"/sample-*; do
  [[ -d "$sample" ]] || continue
  sample_name=$(basename "$sample")
  facts="$sample/pages.tsv"
  dimensions="$sample/namespaces.tsv"
  manifest="$sample/manifest.json"
  read -r dataset_id rows bytes output_rows complete source_exhausted < <(
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); print(d["dataset_id"], d["page_rows"], d["actual_bytes"], d["output_rows"], int(d["complete"]), int(d.get("source_exhausted", False)))' "$manifest"
  )
  if [[ "$complete" != "1" && "$source_exhausted" != "1" ]]; then
    echo "Incomplete sample without an exhausted authentic source: $sample" >&2
    exit 1
  fi

  hdfs_input="$hdfs_input_root/$sample_name"
  if hdfs dfs -test -e "$hdfs_input"; then
    echo "Immutable HDFS input already exists: $hdfs_input" >&2
    exit 1
  fi
  hdfs dfs -mkdir -p "$hdfs_input"
  hdfs dfs -D dfs.replication=2 -put "$facts" "$hdfs_input/pages.tsv"
  hdfs dfs -D dfs.replication=2 -put "$dimensions" "$hdfs_input/namespaces.tsv"
  hdfs fsck "$hdfs_input" -files -blocks -locations >"$runtime_root/$sample_name-fsck.txt" 2>&1
  grep -q 'is HEALTHY' "$runtime_root/$sample_name-fsck.txt"

  # SQLite is mandatory through 10 GiB. At larger sizes it runs only when
  # five input-size equivalents remain free for three databases plus margin.
  sqlite_allowed=1
  available_local=$(df -B1 --output=avail "$sample" | awk 'NR==2 {print $1}')
  if (( bytes <= 10737418240 && available_local < bytes * 4 )); then
    echo "Insufficient local workspace for required SQLite runs: $sample" >&2
    exit 1
  fi
  if (( bytes > 10737418240 )); then
    (( available_local >= bytes * 5 )) || sqlite_allowed=0
  fi

  for run in 1 2 3; do
    run_dir="$runtime_root/$sample_name/run-$run"
    mkdir -p "$run_dir"
    if (( sqlite_allowed )); then
      python3 "$repo_root/common/benchmark/run_timed.py" \
        --label relational-query --engine sqlite --dataset-id "$dataset_id" \
        --manifest "$run_dir/sqlite.json" --input-rows "$rows" \
        --input-bytes "$bytes" --output-rows "$output_rows" -- \
        python3 "$script_dir/sqlite_benchmark.py" "$facts" "$dimensions" \
          "$run_dir/sqlite.db" "$run_dir/sqlite.tsv"
    elif [[ $run -eq 1 ]]; then
      printf 'not run—insufficient safe SQLite workspace\n' >"$run_dir/sqlite-not-run.txt"
    fi

    hdfs_output="$hdfs_output_root/$sample_name-run-$run"
    WEEK05_RUNTIME_ROOT="$run_dir" bash "$script_dir/mapreduce/run-hadoop.sh" \
      "$hdfs_input/pages.tsv" "$hdfs_input/namespaces.tsv" "$hdfs_output" \
      "$dataset_id" "$rows" "$bytes" "$output_rows"
    hdfs dfs -cat "$hdfs_output/part-*" >"$run_dir/hadoop.tsv"
    if (( sqlite_allowed )); then
      python3 "$script_dir/verify_results.py" "$run_dir/sqlite.tsv" "$run_dir/hadoop.tsv"
    fi
  done
done

python3 "$script_dir/summarize_runs.py" "$runtime_root" "$runtime_root/runtime-summary.csv"
