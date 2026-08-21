#!/bin/bash
#
# f2b-sync-to-secondary.sh
#
# Pushes currently-banned IPs from this host's fail2ban jails to a
# secondary fail2ban instance over SSH, using a single interactive
# fail2ban-client session.
#
# Uses the existing passwordless SSH trust from the pi user on
# pihole1 -> pihole2, invoking fail2ban-client via sudo on both ends.
#
# All output goes to stdout/stderr — systemd captures and tags it
# with this unit automatically, so `journalctl -u f2b-sync.service`
# shows everything without needing a separate syslog tag.

set -u

REMOTE_HOST="pihole2"
REMOTE_USER="pi"
SSH_OPTS="-T -o BatchMode=yes -o ConnectTimeout=5"

# Bail out early and loudly if the secondary is unreachable.
if ! ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" true 2>/dev/null; then
    echo "cannot reach $REMOTE_HOST, skipping this run" >&2
    exit 0
fi

JAILS=$(sudo fail2ban-client status | awk -F'\t' '/Jail list/ {print $2}' | tr ',' ' ')

if [ -z "$JAILS" ]; then
    echo "no jails found, nothing to do"
    exit 0
fi

commands=()
total=0

for jail in $JAILS; do
    if [ -z "$jail" ]; then
        continue
    fi

    # recidive re-bans its IPs into the real jails anyway; skip it.
    if [ "$jail" = "recidive" ]; then
        continue
    fi

    # Grab everything after "Banned IP list:".
    ips=$(sudo fail2ban-client status "$jail" 2>/dev/null | sed -n 's/^.*Banned IP list:[[:space:]]*//p')

    read -r -a ip_list <<< "$ips"
    if [ "${#ip_list[@]}" -eq 0 ]; then
        continue
    fi

    # One banip command per jail, with all of its IPs.
    echo "Banning ${#ip_list[@]} ips in $jail"
    commands+=("set $jail banip ${ip_list[*]}")
    total=$((total + ${#ip_list[@]}))
done

if [ "$total" -eq 0 ]; then
    echo "no banned IPs found, nothing to do"
    exit 0
fi

echo "syncing $total IP(s) to $REMOTE_HOST"
printf '%s\n' "${commands[@]}"

rc=0
printf '%s\n' "${commands[@]}" | ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "sudo fail2ban-client -i" 2>&1 || rc=$?

echo

if [ "$rc" -eq 0 ]; then
    echo "sync batch completed: $total IP(s) sent to $REMOTE_HOST"
else
    echo "sync batch to $REMOTE_HOST failed with exit code $rc" >&2
fi

exit 0