#!/usr/bin/env bash
# One-time upload: copy the day's 24 gzip hour files from a local folder on
# the controller into a NEW HDFS folder.  Refuses if the HDFS folder already
# exists, so it can never overwrite or mix with earlier data.  The files stay
# gzipped; Hadoop reads gzip directly, one map task per file.
#
# Usage: upload-pageviews-hdfs.sh LOCAL_DIR /new/hdfs/input-dir
set -euo pipefail

if [[ $# -ne 2 || "$2" != /* ]]; then
  echo "Usage: bash $0 LOCAL_DIR /new/hdfs/input-dir" >&2
  exit 2
fi
local_dir=$1
target=${2%/}

shopt -s nullglob
files=("$local_dir"/pageviews-*.gz)
shopt -u nullglob
[[ ${#files[@]} -eq 24 ]] || {
  echo "Expected 24 pageviews-*.gz files in $local_dir, found ${#files[@]}" >&2
  exit 1
}

# shellcheck disable=SC1091
source /etc/profile.d/hadoop.sh
if hdfs dfs -test -e "$target"; then
  echo "Refusing to upload into existing HDFS path: $target" >&2
  exit 1
fi
hdfs dfs -mkdir -p "$target"
hdfs dfs -put "${files[@]}" "$target/"

# Read-only checks: every file arrived and HDFS reports the folder healthy.
uploaded=$(hdfs dfs -ls "$target" | grep -c 'pageviews-.*\.gz$' || true)
[[ "$uploaded" -eq 24 ]] || { echo "Expected 24 files in $target, found $uploaded" >&2; exit 1; }
hdfs fsck "$target" | grep 'is HEALTHY'
hdfs dfs -du -s -h "$target"
