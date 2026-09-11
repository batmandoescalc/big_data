#!/usr/bin/env bash
# hadoop-poc-rhel9.sh
# Minimal interactive Hadoop "crash course" + Proof-of-Concept installer for 4 RHEL9 VMs:
#   hadoop-0 (NameNode + ResourceManager) and hadoop-1..3 (DataNode + NodeManager)
#
# What this script does:
# - Installs Java + creates hadoop user
# - Downloads Hadoop binary distribution
# - Uses local systemd services; does not provision SSH keys
# - Writes core-site.xml, hdfs-site.xml, mapred-site.xml, yarn-site.xml
# - Formats HDFS (on hadoop-0 only) and starts HDFS + YARN
# - Performs a quick smoke test and prints useful URLs/commands
#
# Run on EACH node as root:
#   sudo bash hadoop-poc-rhel9.sh
#
# Assumptions:
# - Supply the real, resolvable controller and worker names at the prompts
# - You want a quick POC (not hardened, not HA)
# - RHEL9 repos available
#
# Notes:
# - Default Hadoop version: 3.4.3 (change when prompted)
# - Uses systemd services for HDFS/YARN components
# - Uses /data/hadoop/{hdfs,nm,tmp} by default
#
# Prepare and mount the assigned data disk before running this installer.
# Use --check to validate the answers and prerequisites without changing the VM.

set -euo pipefail

# ---------- helpers ----------
die() { echo "ERROR: $*" >&2; exit 1; }
need_root() { [[ $EUID -eq 0 ]] || die "Run as root (sudo)."; }
cmd() { echo "+ $*"; "$@"; }

ask() {
  local prompt="$1" default="${2:-}"
  local ans=""
  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " ans || die "Input ended at: $prompt"
    echo "${ans:-$default}"
  else
    read -r -p "$prompt: " ans || die "Input ended at: $prompt"
    echo "$ans"
  fi
}

ask_yn() {
  local prompt="$1" default="${2:-y}"
  local ans=""
  local hint="y/N"
  [[ "$default" =~ ^[Yy]$ ]] && hint="Y/n"
  read -r -p "$prompt ($hint): " ans || die "Input ended at: $prompt"
  ans="${ans:-$default}"
  [[ "$ans" =~ ^[Yy]$ ]]
}

validate_host() {
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || die "Invalid hostname: $1"
  getent ahostsv4 "$1" >/dev/null || die "Hostname does not resolve: $1"
}

validate_storage() {
  [[ "$DATA_MOUNT" =~ ^/[A-Za-z0-9_/-]+$ && "$DATA_MOUNT" != / ]] || die "Invalid data mount point."
  [[ "$DATA_BASE" =~ ^/[A-Za-z0-9_/-]+$ ]] || die "Invalid data directory."
  [[ "$(realpath -m "$DATA_MOUNT")" == "$DATA_MOUNT" ]] || die "Use a canonical data mount path."
  [[ "$(realpath -m "$DATA_BASE")" == "$DATA_BASE" ]] || die "Use a canonical data directory path."
  [[ "$DATA_BASE" == "$DATA_MOUNT/"* ]] || die "Data directory must be beneath the data mount."
  [[ ! -e "$DATA_BASE" || -d "$DATA_BASE" ]] || die "Data path exists and is not a directory."
  mountpoint -q "$DATA_MOUNT" || die "Mount the assigned data disk at $DATA_MOUNT first."
  [[ "$(findmnt -n -o MAJ:MIN -T "$DATA_MOUNT")" != "$(findmnt -n -o MAJ:MIN -T /)" ]] || die "Data must not be on the root filesystem."
  case ",$(findmnt -n -o OPTIONS -T "$DATA_MOUNT")," in
    *,noexec,*|*,ro,*) die "The data mount must allow writes and YARN task execution." ;;
  esac
  [[ "$(findmnt -n -o FSTYPE -T "$DATA_MOUNT")" =~ ^(xfs|ext4)$ ]] || die "Expected a local XFS or ext4 data filesystem."
  if [[ -e "$DATA_BASE" ]] && [[ -n "$(find "$DATA_BASE" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    die "Existing data found at $DATA_BASE. This installer only handles a fresh cluster."
  fi
}

create_data_dirs() {
  # Set ownership and mode on every ancestor. RHEL's root umask can otherwise
  # leave intermediate directories inaccessible to the Hadoop service account.
  cmd install -d -o "$HADOOP_USER" -g "$HADOOP_GROUP" -m 0750 \
    "$DATA_BASE" "$DATA_BASE/hdfs" "$DATA_BASE/nm" \
    "$HDFS_NAMENODE_DIR" "$HDFS_DATANODE_DIR" \
    "$YARN_NM_LOCAL_DIR" "$YARN_NM_LOG_DIR" "$HADOOP_TMP_DIR" "$DATA_BASE/logs"
}

# ---------- script begins ----------
CHECK_ONLY=no
case "${1:-}" in
  --check) CHECK_ONLY=yes ;;
  --help) echo "Usage: $0 [--check] (interactive, run as root on each prepared VM)"; exit 0 ;;
  "") ;;
  *) die "Unknown argument: $1" ;;
esac
[[ $# -le 1 ]] || die "Too many arguments."
need_root
# shellcheck disable=SC1091
source /etc/os-release
[[ "$ID" == rhel && "$VERSION_ID" == 9.* ]] || die "This installer requires RHEL 9."

echo "Hadoop POC installer for RHEL9 (4-node cluster)."

# Roles: default: hadoop-0 = master, others = workers.
THIS_HOST="$(hostname -s)"
DEFAULT_MASTER="hadoop-0"

MASTER_HOST="$(ask "Master hostname (NameNode/ResourceManager)" "$DEFAULT_MASTER")"
WORKERS_DEFAULT="hadoop-1,hadoop-2,hadoop-3"
WORKERS_CSV="$(ask "Worker hostnames CSV (DataNodes/NodeManagers)" "$WORKERS_DEFAULT")"
IFS=',' read -r -a WORKERS <<<"$WORKERS_CSV"

# Hadoop settings
HADOOP_VERSION="$(ask "Hadoop version" "3.4.3")"
HADOOP_MIRROR="$(ask "Apache mirror base URL" "https://downloads.apache.org/hadoop/common")"
HADOOP_TGZ="hadoop-${HADOOP_VERSION}.tar.gz"
HADOOP_URL="${HADOOP_MIRROR}/hadoop-${HADOOP_VERSION}/${HADOOP_TGZ}"

HADOOP_USER="$(ask "Hadoop service user" "hadoop")"
HADOOP_GROUP="$(ask "Hadoop service group" "hadoop")"
HADOOP_HOME_BASE="/opt"
HADOOP_HOME="${HADOOP_HOME_BASE}/hadoop"
HADOOP_INSTALL_DIR="${HADOOP_HOME_BASE}/hadoop-${HADOOP_VERSION}"

JAVA_PKG="$(ask "Java package (RHEL)" "java-11-openjdk-devel")"

# Data dirs
DATA_MOUNT="$(ask "Prepared data disk mount point" "/data")"
DATA_BASE="$(ask "Base data directory" "${DATA_MOUNT}/hadoop")"
HDFS_NAMENODE_DIR="${DATA_BASE}/hdfs/nn"
HDFS_DATANODE_DIR="${DATA_BASE}/hdfs/dn"
YARN_NM_LOCAL_DIR="${DATA_BASE}/nm/local"
YARN_NM_LOG_DIR="${DATA_BASE}/nm/log"
HADOOP_TMP_DIR="${DATA_BASE}/tmp"

# Ports / UI
NN_RPC_PORT="$(ask "NameNode RPC port" "8020")"
NN_HTTP_PORT="$(ask "NameNode Web UI port" "9870")"
RM_HTTP_PORT="$(ask "ResourceManager Web UI port" "8088")"

# Validate every answer before making any changes.
validate_host "$MASTER_HOST"
[[ "${#WORKERS[@]}" -eq 3 ]] || die "Expected exactly three workers."
declare -A NODE_NAMES=()
for host in "$MASTER_HOST" "${WORKERS[@]}"; do
  validate_host "$host"
  short="${host%%.*}"
  [[ -z "${NODE_NAMES[$short]:-}" ]] || die "Duplicate node: $host"
  NODE_NAMES[$short]=1
done
[[ -n "${NODE_NAMES[$THIS_HOST]:-}" ]] || die "This VM is not in the controller/worker list."
IS_MASTER=no
[[ "$THIS_HOST" != "${MASTER_HOST%%.*}" ]] || IS_MASTER=yes
[[ "$HADOOP_VERSION" =~ ^3\.4\.[0-9]+$ ]] || die "This Java 11 configuration targets Hadoop 3.4.x."
[[ "$HADOOP_MIRROR" == https://downloads.apache.org/hadoop/common ]] || die "Use the official HTTPS download location."
[[ "$HADOOP_USER" =~ ^[a-z_][a-z0-9_-]*$ && "$HADOOP_GROUP" =~ ^[a-z_][a-z0-9_-]*$ ]] || die "Invalid service account."
[[ "$HADOOP_USER" != root && "$HADOOP_GROUP" != root ]] || die "Hadoop must not run as root."
[[ "$JAVA_PKG" == java-11-openjdk-devel ]] || die "This configuration is prepared for Java 11."
for port in "$NN_RPC_PORT" "$NN_HTTP_PORT" "$RM_HTTP_PORT"; do
  [[ "$port" =~ ^[1-9][0-9]{3,4}$ ]] && (( port <= 65535 )) || die "Invalid service port: $port"
done
[[ "$NN_RPC_PORT" != "$NN_HTTP_PORT" && "$NN_RPC_PORT" != "$RM_HTTP_PORT" && "$NN_HTTP_PORT" != "$RM_HTTP_PORT" ]] || die "Service ports must be distinct."
REPL="$(ask "HDFS replication factor" "2")"
[[ "$REPL" =~ ^[123]$ ]] || die "Replication must be between 1 and 3."
(( $(awk '/^MemTotal:/ {print int($2 / 1024)}' /proc/meminfo) >= 7168 )) || die "This configuration requires at least 7 GiB RAM."
(( $(nproc) >= 4 )) || die "This configuration requires at least four CPUs."
validate_storage
[[ ! -e "$HADOOP_HOME" && ! -L "$HADOOP_HOME" && ! -e "$HADOOP_INSTALL_DIR" ]] || die "Existing Hadoop installation found. Inspect it before proceeding."
[[ ! -e /etc/profile.d/hadoop.sh ]] || die "Existing Hadoop environment found."
if compgen -G '/etc/systemd/system/hadoop-*.service' >/dev/null; then
  die "Existing Hadoop services found. Inspect them before proceeding."
fi
if id "$HADOOP_USER" >/dev/null 2>&1; then
  die "The service account already exists. Inspect it before provisioning a fresh cluster."
fi
NODE_ROLE=worker
[[ "$IS_MASTER" != yes ]] || NODE_ROLE=controller
printf 'Validated role: %s; mounted data: %s; Hadoop: %s\n' "$NODE_ROLE" "$DATA_BASE" "$HADOOP_VERSION"
if [[ "$CHECK_ONLY" == yes ]]; then
  echo "Read-only checks passed. Network connectivity and worker resources still require verification."
  exit 0
fi
ask_yn "Install this fresh Hadoop node with the settings above?" n || die "Installation cancelled."

echo "Installing dependencies..."
cmd dnf -y --setopt=install_weak_deps=False install "$JAVA_PKG" curl tar procps-ng

# Create user/group
if ! getent group "$HADOOP_GROUP" >/dev/null; then
  cmd groupadd --system "$HADOOP_GROUP"
fi
if ! id "$HADOOP_USER" >/dev/null 2>&1; then
  cmd useradd --system -g "$HADOOP_GROUP" -m -s /bin/bash "$HADOOP_USER"
fi

# Verify the official archive before extracting it. Keep temporary paths private.
DOWNLOAD_DIR="$(mktemp -d /var/tmp/hadoop-download.XXXXXXXX)"
trap 'rm -rf -- "$DOWNLOAD_DIR"' EXIT
cmd curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --retry 3 -o "$DOWNLOAD_DIR/$HADOOP_TGZ" "$HADOOP_URL"
cmd curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --retry 3 -o "$DOWNLOAD_DIR/archive.sha512" "${HADOOP_URL}.sha512"
EXPECTED_HASH="$(grep -Eo '[A-Fa-f0-9]{128}' "$DOWNLOAD_DIR/archive.sha512")"
[[ "$EXPECTED_HASH" =~ ^[A-Fa-f0-9]{128}$ ]] || die "Invalid SHA-512 checksum response."
ACTUAL_HASH="$(sha512sum "$DOWNLOAD_DIR/$HADOOP_TGZ")"
ACTUAL_HASH="${ACTUAL_HASH%% *}"
[[ "${EXPECTED_HASH,,}" == "$ACTUAL_HASH" ]] || die "Hadoop archive checksum mismatch."
cmd tar --no-same-owner -C "$HADOOP_HOME_BASE" -xzf "$DOWNLOAD_DIR/$HADOOP_TGZ"

# Symlink /opt/hadoop -> /opt/hadoop-x.y.z
cmd ln -sfn "$HADOOP_INSTALL_DIR" "$HADOOP_HOME"
cmd chown -R "$HADOOP_USER:$HADOOP_GROUP" "$HADOOP_INSTALL_DIR"

# Create all data directories with explicit ownership, including ancestors.
create_data_dirs
cmd restorecon "$DATA_MOUNT"
cmd restorecon -RF "$DATA_BASE"

# Select Java 11 explicitly without changing the machine's default Java.
JAVA_HOME_PATH="$(readlink -f /usr/lib/jvm/java-11-openjdk)"
[[ -x "$JAVA_HOME_PATH/bin/java" ]] || die "Java 11 installation could not be located."

HADOOP_PROFILE="/etc/profile.d/hadoop.sh"
cat >"$HADOOP_PROFILE" <<EOF
# Hadoop env (POC)
export JAVA_HOME="${JAVA_HOME_PATH}"
export HADOOP_HOME="${HADOOP_HOME}"
export HADOOP_CONF_DIR="\$HADOOP_HOME/etc/hadoop"
export HADOOP_MAPRED_HOME="\$HADOOP_HOME"
export HADOOP_COMMON_HOME="\$HADOOP_HOME"
export HADOOP_HDFS_HOME="\$HADOOP_HOME"
export HADOOP_YARN_HOME="\$HADOOP_HOME"
export HADOOP_LOG_DIR="${DATA_BASE}/logs"
export HADOOP_HEAPSIZE_MAX="1g"
export PATH="\$PATH:\$HADOOP_HOME/bin:\$HADOOP_HOME/sbin"
EOF
chmod 0644 "$HADOOP_PROFILE"

# Also set JAVA_HOME in hadoop-env.sh
HENV="${HADOOP_HOME}/etc/hadoop/hadoop-env.sh"
if ! grep -q '^export JAVA_HOME=' "$HENV"; then
  echo "export JAVA_HOME=${JAVA_HOME_PATH}" >>"$HENV"
else
  sed -ri "s|^export JAVA_HOME=.*|export JAVA_HOME=${JAVA_HOME_PATH}|" "$HENV"
fi

# Configure workers file
WORKERS_FILE="${HADOOP_HOME}/etc/hadoop/workers"
: > "$WORKERS_FILE"
for w in "${WORKERS[@]}"; do
  echo "$w" >>"$WORKERS_FILE"
done
chown "$HADOOP_USER:$HADOOP_GROUP" "$WORKERS_FILE"

# Write XML configs
CONF_DIR="${HADOOP_HOME}/etc/hadoop"

# core-site.xml
cat >"${CONF_DIR}/core-site.xml" <<EOF
<?xml version="1.0"?>
<configuration>
  <property>
    <name>fs.defaultFS</name>
    <value>hdfs://${MASTER_HOST}:${NN_RPC_PORT}</value>
  </property>
  <property>
    <name>hadoop.tmp.dir</name>
    <value>${HADOOP_TMP_DIR}</value>
  </property>
</configuration>
EOF

# hdfs-site.xml
cat >"${CONF_DIR}/hdfs-site.xml" <<EOF
<?xml version="1.0"?>
<configuration>
  <property>
    <name>dfs.namenode.name.dir</name>
    <value>file://${HDFS_NAMENODE_DIR}</value>
  </property>
  <property>
    <name>dfs.datanode.data.dir</name>
    <value>file://${HDFS_DATANODE_DIR}</value>
  </property>
  <property>
    <name>dfs.replication</name>
    <value>${REPL}</value>
  </property>
  <property>
    <name>dfs.namenode.http-address</name>
    <value>${MASTER_HOST}:${NN_HTTP_PORT}</value>
  </property>
</configuration>
EOF

# mapred-site.xml
cat >"${CONF_DIR}/mapred-site.xml" <<EOF
<?xml version="1.0"?>
<configuration>
  <property>
    <name>mapreduce.framework.name</name>
    <value>yarn</value>
  </property>
  <property>
    <name>mapreduce.application.classpath</name>
    <value>${HADOOP_HOME}/share/hadoop/mapreduce/*:${HADOOP_HOME}/share/hadoop/mapreduce/lib/*</value>
  </property>
</configuration>
EOF

# yarn-site.xml
cat >"${CONF_DIR}/yarn-site.xml" <<EOF
<?xml version="1.0"?>
<configuration>
  <property>
    <name>yarn.resourcemanager.hostname</name>
    <value>${MASTER_HOST}</value>
  </property>
  <property>
    <name>yarn.resourcemanager.webapp.address</name>
    <value>${MASTER_HOST}:${RM_HTTP_PORT}</value>
  </property>
  <property>
    <name>yarn.nodemanager.address</name>
    <value>0.0.0.0:8041</value>
  </property>
  <property>
    <name>yarn.nodemanager.resource.memory-mb</name>
    <value>4096</value>
  </property>
  <property>
    <name>yarn.nodemanager.resource.cpu-vcores</name>
    <value>2</value>
  </property>
  <property>
    <name>yarn.scheduler.maximum-allocation-mb</name>
    <value>4096</value>
  </property>
  <property>
    <name>yarn.nodemanager.env-whitelist</name>
    <value>JAVA_HOME,HADOOP_COMMON_HOME,HADOOP_HDFS_HOME,HADOOP_CONF_DIR,CLASSPATH_PREPEND_DISTCACHE,HADOOP_YARN_HOME,HADOOP_HOME,PATH,LANG,TZ,HADOOP_MAPRED_HOME</value>
  </property>
  <property>
    <name>yarn.nodemanager.aux-services</name>
    <value>mapreduce_shuffle</value>
  </property>
  <property>
    <name>yarn.nodemanager.local-dirs</name>
    <value>${YARN_NM_LOCAL_DIR}</value>
  </property>
  <property>
    <name>yarn.nodemanager.log-dirs</name>
    <value>${YARN_NM_LOG_DIR}</value>
  </property>
</configuration>
EOF

chown -R "$HADOOP_USER:$HADOOP_GROUP" "$CONF_DIR"

# systemd units: run daemons without relying on ssh fanout.
# Master: namenode + resourcemanager
# Workers: datanode + nodemanager
SYSTEMD_DIR="/etc/systemd/system"

write_unit() {
  local unit="$1" content="$2"
  echo "$content" > "${SYSTEMD_DIR}/${unit}"
  chmod 0644 "${SYSTEMD_DIR}/${unit}"
}


DAEMON_ENV="Environment=JAVA_HOME=${JAVA_HOME_PATH}
Environment=HADOOP_HOME=${HADOOP_HOME}
Environment=HADOOP_CONF_DIR=${HADOOP_HOME}/etc/hadoop
Environment=HADOOP_MAPRED_HOME=${HADOOP_HOME}
Environment=HADOOP_COMMON_HOME=${HADOOP_HOME}
Environment=HADOOP_HDFS_HOME=${HADOOP_HOME}
Environment=HADOOP_YARN_HOME=${HADOOP_HOME}
Environment=HADOOP_LOG_DIR=${DATA_BASE}/logs
Environment=HADOOP_HEAPSIZE_MAX=1g
Environment=PATH=/usr/sbin:/usr/bin:${HADOOP_HOME}/bin:${HADOOP_HOME}/sbin"

# NameNode unit (master only)
NN_UNIT="[Unit]
Description=Hadoop HDFS NameNode
After=network-online.target
Wants=network-online.target
RequiresMountsFor=${DATA_MOUNT}
ConditionPathIsMountPoint=${DATA_MOUNT}

[Service]
Type=simple
User=${HADOOP_USER}
Group=${HADOOP_GROUP}
${DAEMON_ENV}
ExecStart=${HADOOP_HOME}/bin/hdfs namenode
TimeoutStopSec=120
RestartSec=5
Restart=on-failure

[Install]
WantedBy=multi-user.target
"

# DataNode unit (workers only)
DN_UNIT="[Unit]
Description=Hadoop HDFS DataNode
After=network-online.target
Wants=network-online.target
RequiresMountsFor=${DATA_MOUNT}
ConditionPathIsMountPoint=${DATA_MOUNT}

[Service]
Type=simple
User=${HADOOP_USER}
Group=${HADOOP_GROUP}
${DAEMON_ENV}
ExecStart=${HADOOP_HOME}/bin/hdfs datanode
TimeoutStopSec=120
RestartSec=5
Restart=on-failure

[Install]
WantedBy=multi-user.target
"

# ResourceManager unit (master only)
RM_UNIT="[Unit]
Description=Hadoop YARN ResourceManager
After=network-online.target
Wants=network-online.target
RequiresMountsFor=${DATA_MOUNT}
ConditionPathIsMountPoint=${DATA_MOUNT}

[Service]
Type=simple
User=${HADOOP_USER}
Group=${HADOOP_GROUP}
${DAEMON_ENV}
ExecStart=${HADOOP_HOME}/bin/yarn resourcemanager
TimeoutStopSec=120
RestartSec=5
Restart=on-failure

[Install]
WantedBy=multi-user.target
"

# NodeManager unit (workers only)
NM_UNIT="[Unit]
Description=Hadoop YARN NodeManager
After=network-online.target
Wants=network-online.target
RequiresMountsFor=${DATA_MOUNT}
ConditionPathIsMountPoint=${DATA_MOUNT}

[Service]
Type=simple
User=${HADOOP_USER}
Group=${HADOOP_GROUP}
${DAEMON_ENV}
ExecStart=${HADOOP_HOME}/bin/yarn nodemanager
TimeoutStopSec=120
RestartSec=5
Restart=on-failure

[Install]
WantedBy=multi-user.target
"

if [[ "$IS_MASTER" == yes ]]; then
  write_unit "hadoop-hdfs-namenode.service" "$NN_UNIT"
  write_unit "hadoop-yarn-resourcemanager.service" "$RM_UNIT"
else
  write_unit "hadoop-hdfs-datanode.service" "$DN_UNIT"
  write_unit "hadoop-yarn-nodemanager.service" "$NM_UNIT"
fi
cmd systemctl daemon-reload

# Fresh-node validation above rejects pre-existing data. Never force a format.
if [[ "$IS_MASTER" == yes ]]; then
  [[ ! -e "${HDFS_NAMENODE_DIR}/current" ]] || die "Existing NameNode metadata detected."
  ask_yn "Initialize the new HDFS namespace on this fresh controller?" n || die "Initialization cancelled; services have not started."
  cmd sudo -u "$HADOOP_USER" env "JAVA_HOME=$JAVA_HOME_PATH" "HADOOP_LOG_DIR=${DATA_BASE}/logs" "${HADOOP_HOME}/bin/hdfs" namenode -format -nonInteractive
  cmd systemctl enable --now hadoop-hdfs-namenode.service hadoop-yarn-resourcemanager.service
  cmd systemctl is-active hadoop-hdfs-namenode.service hadoop-yarn-resourcemanager.service
  # An active process is not necessarily ready to accept HDFS requests.
  ready=no
  for attempt in {1..20}; do
    if sudo -u "$HADOOP_USER" env "JAVA_HOME=$JAVA_HOME_PATH" timeout 5 "${HADOOP_HOME}/bin/hdfs" dfsadmin -report >/dev/null 2>&1; then
      ready=yes
      break
    fi
    sleep 2
  done
  [[ "$ready" == yes ]] || die "NameNode did not become ready. Check its systemd journal."
else
  cmd systemctl enable --now hadoop-hdfs-datanode.service hadoop-yarn-nodemanager.service
  sleep 5
  cmd systemctl is-active hadoop-hdfs-datanode.service hadoop-yarn-nodemanager.service
fi

# Quick checks
echo
echo "=== Quick checks ==="
if [[ "$IS_MASTER" == "yes" ]]; then
  echo "JPS (master):"
  cmd sudo -u "$HADOOP_USER" bash -lc "source /etc/profile.d/hadoop.sh && jps"

  echo
  echo "Try HDFS report:"
  cmd sudo -u "$HADOOP_USER" bash -lc "source /etc/profile.d/hadoop.sh && hdfs dfsadmin -report"

  echo "After all three workers are installed, run scripts/verify-cluster.sh as the Hadoop service account."
else
  echo "JPS (worker):"
  cmd sudo -u "$HADOOP_USER" bash -lc "source /etc/profile.d/hadoop.sh && jps"
fi

echo
echo "=== UI URLs (from your browser) ==="
echo "NameNode UI:       http://${MASTER_HOST}:${NN_HTTP_PORT}/"
echo "ResourceManager UI:http://${MASTER_HOST}:${RM_HTTP_PORT}/"

echo
echo "=== Useful commands (run as ${HADOOP_USER} on master) ==="
cat <<EOF
source /etc/profile.d/hadoop.sh
hdfs dfsadmin -report
yarn node -list
yarn application -list
hdfs dfs -ls /
EOF

echo
echo "Done."
echo "If workers aren't showing up, verify:"
echo "- DNS/hosts resolution between nodes"
echo "- time sync (chronyd) is sane"
echo "- narrowly scoped Hadoop firewall rules between the four nodes"
echo "- services: systemctl status hadoop-*"
