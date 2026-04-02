#!/usr/bin/env bash
# hadoop-poc-rhel9.sh
# Minimal interactive Hadoop "crash course" + Proof-of-Concept installer for 4 RHEL9 VMs:
#   hadoop-0 (NameNode + ResourceManager) and hadoop-1..3 (DataNode + NodeManager)
#
# What this script does:
# - Installs Java + creates hadoop user
# - Downloads Hadoop binary distribution
# - Sets up passwordless SSH (optional, recommended)
# - Writes core-site.xml, hdfs-site.xml, mapred-site.xml, yarn-site.xml
# - Formats HDFS (on hadoop-0 only) and starts HDFS + YARN
# - Performs a quick smoke test and prints useful URLs/commands
#
# Run on EACH node as root:
#   sudo bash hadoop-poc-rhel9.sh
#
# Assumptions:
# - Hostnames: hadoop-0..hadoop-3 resolve correctly (DNS or /etc/hosts)
# - You want a quick POC (not hardened, not HA)
# - RHEL9 repos available
#
# Notes:
# - Default Hadoop version: 3.3.6 (change when prompted)
# - Uses systemd services for HDFS/YARN components
# - Uses /data/hadoop/{hdfs,nm,tmp} by default
#
# If you want this to also manage /etc/hosts, say yes when prompted.

set -euo pipefail

# ---------- helpers ----------
die() { echo "ERROR: $*" >&2; exit 1; }
need_root() { [[ $EUID -eq 0 ]] || die "Run as root (sudo)."; }
cmd() { echo "+ $*"; "$@"; }
have() { command -v "$1" >/dev/null 2>&1; }

ask() {
  local prompt="$1" default="${2:-}"
  local ans=""
  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " ans || true
    echo "${ans:-$default}"
  else
    read -r -p "$prompt: " ans || true
    echo "$ans"
  fi
}

ask_yn() {
  local prompt="$1" default="${2:-y}"
  local ans=""
  local hint="y/N"
  [[ "$default" =~ ^[Yy]$ ]] && hint="Y/n"
  read -r -p "$prompt ($hint): " ans || true
  ans="${ans:-$default}"
  [[ "$ans" =~ ^[Yy]$ ]]
}

assert_hostname() {
  local hn
  hn="$(hostname -s)"
  if [[ ! "$hn" =~ ^hadoop-[0-3]$ ]]; then
    echo "WARNING: Hostname is '$hn' but expected hadoop-0..hadoop-3."
    echo "This is OK if you configure roles/hosts correctly, but defaults assume those names."
  fi
}

append_hosts_if_needed() {
  local do_hosts="$1"
  [[ "$do_hosts" == "yes" ]] || return 0

  echo "Enter the IPs for each host (used to populate /etc/hosts)."
  local ip0 ip1 ip2 ip3
  ip0="$(ask "IP for hadoop-0")"
  ip1="$(ask "IP for hadoop-1")"
  ip2="$(ask "IP for hadoop-2")"
  ip3="$(ask "IP for hadoop-3")"

  for pair in \
    "$ip0 hadoop-0" \
    "$ip1 hadoop-1" \
    "$ip2 hadoop-2" \
    "$ip3 hadoop-3"
  do
    local ip host
    ip="$(awk '{print $1}' <<<"$pair")"
    host="$(awk '{print $2}' <<<"$pair")"
    [[ -n "$ip" && -n "$host" ]] || die "Missing IP/host for /etc/hosts."
    if ! grep -qE "^[[:space:]]*$ip[[:space:]].*\b$host\b" /etc/hosts; then
      echo "Adding to /etc/hosts: $ip $host"
      echo "$ip $host" >> /etc/hosts
    else
      echo "/etc/hosts already has: $ip $host"
    fi
  done
}

write_file() {
  local path="$1"
  shift
  install -d -m 0755 "$(dirname "$path")"
  cat >"$path" <<'EOF'
'"$@"'
EOF
}

xml_escape() {
  sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/"/\&quot;/g' -e "s/'/\&apos;/g"
}

# ---------- script begins ----------
need_root
assert_hostname

echo "Hadoop POC installer for RHEL9 (4-node cluster)."

# Roles: default: hadoop-0 = master, others = workers.
THIS_HOST="$(hostname -s)"
DEFAULT_MASTER="hadoop-0"

MASTER_HOST="$(ask "Master hostname (NameNode/ResourceManager)" "$DEFAULT_MASTER")"
WORKERS_DEFAULT="hadoop-1,hadoop-2,hadoop-3"
WORKERS_CSV="$(ask "Worker hostnames CSV (DataNodes/NodeManagers)" "$WORKERS_DEFAULT")"
IFS=',' read -r -a WORKERS <<<"$WORKERS_CSV"

# Network/hosts
if ask_yn "Do you want to populate /etc/hosts with hadoop-0..3 IPs?" "n"; then
  append_hosts_if_needed "yes"
fi

# Hadoop settings
HADOOP_VERSION="$(ask "Hadoop version" "3.3.6")"
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
DATA_BASE="$(ask "Base data directory" "/data/hadoop")"
HDFS_NAMENODE_DIR="${DATA_BASE}/hdfs/nn"
HDFS_DATANODE_DIR="${DATA_BASE}/hdfs/dn"
YARN_NM_LOCAL_DIR="${DATA_BASE}/nm/local"
YARN_NM_LOG_DIR="${DATA_BASE}/nm/log"
HADOOP_TMP_DIR="${DATA_BASE}/tmp"

# Ports / UI
NN_RPC_PORT="$(ask "NameNode RPC port" "8020")"
NN_HTTP_PORT="$(ask "NameNode Web UI port" "9870")"
RM_HTTP_PORT="$(ask "ResourceManager Web UI port" "8088")"

# Optional: disable firewall/selinux (POC)
if ask_yn "POC-only: set SELinux to permissive now?" "n"; then
  if have getenforce; then
    cmd setenforce 0 || true
    sed -ri 's/^SELINUX=.*/SELINUX=permissive/' /etc/selinux/config || true
  fi
fi
if ask_yn "POC-only: stop+disable firewalld now?" "n"; then
  cmd systemctl disable --now firewalld || true
fi

echo "Installing dependencies..."
cmd dnf -y install "$JAVA_PKG" wget tar openssh-clients rsync procps-ng

# Create user/group
if ! getent group "$HADOOP_GROUP" >/dev/null; then
  cmd groupadd --system "$HADOOP_GROUP"
fi
if ! id "$HADOOP_USER" >/dev/null 2>&1; then
  cmd useradd --system -g "$HADOOP_GROUP" -m -s /bin/bash "$HADOOP_USER"
fi

# Install Hadoop
if [[ ! -d "$HADOOP_INSTALL_DIR" ]]; then
  echo "Downloading Hadoop: $HADOOP_URL"
  cmd wget -O "/tmp/${HADOOP_TGZ}" "$HADOOP_URL"
  cmd tar -C "$HADOOP_HOME_BASE" -xzf "/tmp/${HADOOP_TGZ}"
fi

# Symlink /opt/hadoop -> /opt/hadoop-x.y.z
cmd ln -sfn "$HADOOP_INSTALL_DIR" "$HADOOP_HOME"
cmd chown -R "$HADOOP_USER:$HADOOP_GROUP" "$HADOOP_INSTALL_DIR"

# Create dirs
for d in "$HDFS_NAMENODE_DIR" "$HDFS_DATANODE_DIR" "$YARN_NM_LOCAL_DIR" "$YARN_NM_LOG_DIR" "$HADOOP_TMP_DIR"; do
  cmd mkdir -p "$d"
  cmd chown -R "$HADOOP_USER:$HADOOP_GROUP" "$d"
  cmd chmod 0755 "$d"
done

# Environment for hadoop user
JAVA_HOME_PATH="$(dirname "$(dirname "$(readlink -f "$(command -v javac 2>/dev/null || command -v java)")")")"
if [[ -z "$JAVA_HOME_PATH" || ! -d "$JAVA_HOME_PATH" ]]; then
  # Fallback: common path for RHEL
  JAVA_HOME_PATH="/usr/lib/jvm/java-11-openjdk"
fi

HADOOP_PROFILE="/etc/profile.d/hadoop.sh"
cat >"$HADOOP_PROFILE" <<EOF
# Hadoop env (POC)
export JAVA_HOME="${JAVA_HOME_PATH}"
export HADOOP_HOME="${HADOOP_HOME}"
export HADOOP_CONF_DIR="\$HADOOP_HOME/etc/hadoop"
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
REPL="$(ask "HDFS replication factor (for 3 workers use 2 or 3)" "2")"
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

# Optional: SSH keys for hadoop user (needed for start-dfs.sh / start-yarn.sh to fan out)
if ask_yn "Set up passwordless SSH for ${HADOOP_USER} to all nodes (recommended)?" "y"; then
  # Ensure sshd is up
  cmd systemctl enable --now sshd

  # Generate key if missing
  if [[ ! -f "/home/${HADOOP_USER}/.ssh/id_ed25519" ]]; then
    cmd sudo -u "$HADOOP_USER" mkdir -p "/home/${HADOOP_USER}/.ssh"
    cmd sudo -u "$HADOOP_USER" chmod 700 "/home/${HADOOP_USER}/.ssh"
    cmd sudo -u "$HADOOP_USER" ssh-keygen -t ed25519 -N "" -f "/home/${HADOOP_USER}/.ssh/id_ed25519"
  fi

  PUBKEY="$(cat "/home/${HADOOP_USER}/.ssh/id_ed25519.pub")"

  # Add to local authorized_keys
  AUTH="/home/${HADOOP_USER}/.ssh/authorized_keys"
  touch "$AUTH"
  chown "$HADOOP_USER:$HADOOP_GROUP" "$AUTH"
  chmod 600 "$AUTH"
  grep -qF "$PUBKEY" "$AUTH" || echo "$PUBKEY" >>"$AUTH"

  echo "Now we need to copy the public key to other nodes' ${HADOOP_USER} accounts."
  echo "This requires that the ${HADOOP_USER} account exists on all nodes (we created it)."
  echo "If SSH prompts for a password, enter the ${HADOOP_USER} password (or use root provisioning)."

  # Ensure the hadoop user can SSH without strict prompts
  SSHCFG="/home/${HADOOP_USER}/.ssh/config"
  if [[ ! -f "$SSHCFG" ]]; then
    cat >"$SSHCFG" <<EOF
Host hadoop-*
  StrictHostKeyChecking no
  UserKnownHostsFile=/dev/null
EOF
    chown "$HADOOP_USER:$HADOOP_GROUP" "$SSHCFG"
    chmod 600 "$SSHCFG"
  fi

  # Set a password if needed (interactive)
  if ask_yn "Do you want to set/reset password for ${HADOOP_USER} on THIS node (helps ssh-copy-id)?" "n"; then
    passwd "$HADOOP_USER"
  fi

  for host in "$MASTER_HOST" "${WORKERS[@]}"; do
    echo "Copying key to $host..."
    # Try ssh-copy-id; if not installed, do a manual append.
    if have ssh-copy-id; then
      cmd sudo -u "$HADOOP_USER" ssh-copy-id -i "/home/${HADOOP_USER}/.ssh/id_ed25519.pub" "${HADOOP_USER}@${host}" || true
    else
      # Manual: append via ssh
      cmd sudo -u "$HADOOP_USER" ssh "${HADOOP_USER}@${host}" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && grep -qF '$PUBKEY' ~/.ssh/authorized_keys || echo '$PUBKEY' >> ~/.ssh/authorized_keys" || true
    fi
  done
fi

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
Environment=PATH=/usr/sbin:/usr/bin:${HADOOP_HOME}/bin:${HADOOP_HOME}/sbin"

# NameNode unit (master only)
NN_UNIT="[Unit]
Description=Hadoop HDFS NameNode
After=network.target

[Service]
Type=forking
User=${HADOOP_USER}
Group=${HADOOP_GROUP}
${DAEMON_ENV}
ExecStart=${HADOOP_HOME}/bin/hdfs --daemon start namenode
ExecStop=${HADOOP_HOME}/bin/hdfs --daemon stop namenode
Restart=on-failure

[Install]
WantedBy=multi-user.target
"

# DataNode unit (all nodes)
DN_UNIT="[Unit]
Description=Hadoop HDFS DataNode
After=network.target

[Service]
Type=forking
User=${HADOOP_USER}
Group=${HADOOP_GROUP}
${DAEMON_ENV}
ExecStart=${HADOOP_HOME}/bin/hdfs --daemon start datanode
ExecStop=${HADOOP_HOME}/bin/hdfs --daemon stop datanode
Restart=on-failure

[Install]
WantedBy=multi-user.target
"

# ResourceManager unit (master only)
RM_UNIT="[Unit]
Description=Hadoop YARN ResourceManager
After=network.target

[Service]
Type=forking
User=${HADOOP_USER}
Group=${HADOOP_GROUP}
${DAEMON_ENV}
ExecStart=${HADOOP_HOME}/bin/yarn --daemon start resourcemanager
ExecStop=${HADOOP_HOME}/bin/yarn --daemon stop resourcemanager
Restart=on-failure

[Install]
WantedBy=multi-user.target
"

# NodeManager unit (all nodes)
NM_UNIT="[Unit]
Description=Hadoop YARN NodeManager
After=network.target

[Service]
Type=forking
User=${HADOOP_USER}
Group=${HADOOP_GROUP}
${DAEMON_ENV}
ExecStart=${HADOOP_HOME}/bin/yarn --daemon start nodemanager
ExecStop=${HADOOP_HOME}/bin/yarn --daemon stop nodemanager
Restart=on-failure

[Install]
WantedBy=multi-user.target
"

write_unit "hadoop-hdfs-datanode.service" "$DN_UNIT"
write_unit "hadoop-yarn-nodemanager.service" "$NM_UNIT"

IS_MASTER="no"
if [[ "$THIS_HOST" == "$MASTER_HOST" ]]; then
  IS_MASTER="yes"
  write_unit "hadoop-hdfs-namenode.service" "$NN_UNIT"
  write_unit "hadoop-yarn-resourcemanager.service" "$RM_UNIT"
fi

cmd systemctl daemon-reload

# Enable services
cmd systemctl enable hadoop-hdfs-datanode.service
cmd systemctl enable hadoop-yarn-nodemanager.service
if [[ "$IS_MASTER" == "yes" ]]; then
  cmd systemctl enable hadoop-hdfs-namenode.service
  cmd systemctl enable hadoop-yarn-resourcemanager.service
fi

# Format HDFS only on master (and only if not already formatted)
if [[ "$IS_MASTER" == "yes" ]]; then
  if [[ ! -d "${HDFS_NAMENODE_DIR}/current" ]]; then
    if ask_yn "Format HDFS NameNode now? (ONLY do this once)" "y"; then
      cmd sudo -u "$HADOOP_USER" "${HADOOP_HOME}/bin/hdfs" namenode -format -force -nonInteractive
    else
      echo "Skipping format. You must format before starting NameNode the first time."
    fi
  else
    echo "NameNode appears already formatted (${HDFS_NAMENODE_DIR}/current exists)."
  fi
fi

# Start services
cmd systemctl restart hadoop-hdfs-datanode.service
cmd systemctl restart hadoop-yarn-nodemanager.service

if [[ "$IS_MASTER" == "yes" ]]; then
  cmd systemctl restart hadoop-hdfs-namenode.service
  cmd systemctl restart hadoop-yarn-resourcemanager.service
fi

# Quick checks
echo
echo "=== Quick checks ==="
if [[ "$IS_MASTER" == "yes" ]]; then
  echo "JPS (master):"
  cmd sudo -u "$HADOOP_USER" bash -lc "source /etc/profile.d/hadoop.sh && jps" || true

  echo
  echo "Try HDFS report:"
  cmd sudo -u "$HADOOP_USER" bash -lc "source /etc/profile.d/hadoop.sh && hdfs dfsadmin -report" || true

  if ask_yn "Run a tiny HDFS smoke test (mkdir/put/ls)?" "y"; then
    cmd sudo -u "$HADOOP_USER" bash -lc "source /etc/profile.d/hadoop.sh && \
      hdfs dfs -mkdir -p /tmp/poc && \
      echo 'hello hadoop' >/tmp/hello.txt && \
      hdfs dfs -put -f /tmp/hello.txt /tmp/poc/hello.txt && \
      hdfs dfs -ls /tmp/poc && \
      hdfs dfs -cat /tmp/poc/hello.txt"
  fi
else
  echo "JPS (worker):"
  cmd sudo -u "$HADOOP_USER" bash -lc "source /etc/profile.d/hadoop.sh && jps" || true
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
echo "- ports allowed (or firewalld off for POC)"
echo "- services: systemctl status hadoop-*"