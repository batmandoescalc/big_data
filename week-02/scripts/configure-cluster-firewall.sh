#!/usr/bin/env bash
# Usage: sudo bash configure-cluster-firewall.sh controller|worker IP0 IP1 IP2 IP3
# Addresses must be the four verified VM addresses, including this VM's address.
set -euo pipefail
die() { echo "ERROR: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die 'Run as root.'
[[ $# -eq 5 ]] || die 'Supply role and exactly four verified IPv4 addresses.'
role=$1
shift
case "$role" in
  controller) ports=(8020 8030-8033 8088 9870) ;;
  worker) ports=(8040-8042 9864 9866-9867 13562 32768-60999) ;;
  *) die 'Role must be controller or worker.' ;;
esac
zone=${HADOOP_FIREWALL_ZONE:-public}
[[ "$zone" =~ ^[a-zA-Z0-9_-]+$ ]] || die 'Invalid zone name.'
firewall-cmd --state
firewall-cmd --get-active-zones | grep -Fxq "$zone" || die 'Expected active firewall zone is absent.'
read -r first_port last_port </proc/sys/net/ipv4/ip_local_port_range
[[ "$first_port" == 32768 && "$last_port" == 60999 ]] || die 'Recheck dynamic YARN port rules against this VM.'
declare -A seen=()
local_matches=0
rules=()
for address in "$@"; do
  [[ "$address" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || die 'Invalid IPv4 address.'
  IFS=. read -r -a octets <<<"$address"
  for octet in "${octets[@]}"; do
    (( 10#$octet <= 255 )) || die 'Invalid IPv4 octet.'
    [[ "$octet" == 0 || "$octet" != 0* ]] || die 'Use canonical IPv4 addresses.'
  done
  [[ -z ${seen[$address]:-} ]] || die 'Duplicate node address.'
  seen[$address]=yes
  if ip -4 -o address show scope global | awk '{split($4, a, "/"); print a[1]}' | grep -Fxq "$address"; then
    local_matches=$((local_matches + 1))
    continue
  fi
  for port in "${ports[@]}"; do
    rules+=("--add-rich-rule=rule family=\"ipv4\" source address=\"$address/32\" port port=\"$port\" protocol=\"tcp\" accept")
  done
done
[[ "$local_matches" -eq 1 ]] || die 'Exactly one supplied address must belong to this VM.'
# Add only the project rules. Do not reload, disable, or replace existing policy.
firewall-cmd --permanent --zone="$zone" "${rules[@]}"
firewall-cmd --zone="$zone" "${rules[@]}"
firewall-cmd --check-config
printf 'Configured %s Hadoop rules for the other three verified nodes.\n' "$role"
