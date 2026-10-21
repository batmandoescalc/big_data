#!/usr/bin/env bash
# preflight.sh - read-only inspection of one Hadoop VM.
# Answers the README's open questions without changing anything.
# Usage: HADOOP_HOSTS="host0 host1 host2 host3" ssh <host> 'HADOOP_HOSTS="..." bash -s' < scripts/preflight.sh
# HADOOP_HOSTS is optional. It lists the cluster FQDNs to test DNS for and is
# kept out of this file on purpose (see README: no internal server details).
set -u

section() { printf '\n=== %s ===\n' "$*"; }

section "Identity"
echo "user: $(whoami)   host: $(hostname -f)   date: $(date -Is)"

section "OS / kernel / uptime"
grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release
uname -r
uptime -p

section "CPU / memory"
nproc
free -h | sed -n '1,2p'

section "Disks and mounts (looking for the 1 TB /dev/sdb data drive)"
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT
echo "--- fstab (non-comment) ---"
grep -vE '^\s*(#|$)' /etc/fstab
echo "--- df ---"
df -hT -x tmpfs -x devtmpfs

section "sudo rights for this account"
sudo -n -l 2>&1 | head -20

section "Existing Hadoop footprint"
id hadoop 2>/dev/null || echo "no 'hadoop' user"
for p in /opt/hadoop /opt/hadoop-* /data/hadoop /etc/profile.d/hadoop.sh; do
  [ -e "$p" ] && echo "EXISTS: $p" || echo "absent: $p"
done
ls /etc/systemd/system/hadoop-* 2>/dev/null || echo "no hadoop systemd units"
command -v java >/dev/null && java -version 2>&1 | head -1 || echo "java: not installed"

section "SELinux / firewall"
getenforce 2>/dev/null || echo "getenforce: n/a"
systemctl is-active firewalld 2>/dev/null || true
sudo -n firewall-cmd --list-all 2>/dev/null || echo "(firewall-cmd needs sudo; skipped)"

section "Time sync"
chronyc tracking 2>/dev/null | head -3 || timedatectl | grep -i synchronized

section "Cluster name resolution from this node"
if [ -n "${HADOOP_HOSTS:-}" ]; then
  for h in $HADOOP_HOSTS; do
    printf '%-40s ' "$h"; getent hosts "$h" | awk '{print $1}' || echo "UNRESOLVED"
  done
else
  echo "HADOOP_HOSTS not set; skipping cross-node DNS check"
fi
grep -i hadoop /etc/hosts || echo "/etc/hosts has no hadoop entries"

section "Listening ports"
ss -ltnp 2>/dev/null | awk 'NR==1 || /:(22|8020|9870|8088|9864|9866|8042)\s/'

section "Authorized keys on this account"
[ -f ~/.ssh/authorized_keys ] && awk '{print $1, $3}' ~/.ssh/authorized_keys || echo "no authorized_keys yet"
