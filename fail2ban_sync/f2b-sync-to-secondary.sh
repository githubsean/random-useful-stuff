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

if [ -z "$JAILS" ]; then
    JAILS=$(sudo fail2ban-client status | awk -F'\t' '/Jail list/ {print $2}' | tr ',' ' ')
fi

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

    # Grab everything after "Banned IP list:".
    ips=$(sudo fail2ban-client status "$jail" 2>/dev/null | sed -n 's/^.*Banned IP list:[[:space:]]*//p')

    for ip in $ips; do
        if [ -z "$ip" ]; then
            continue
        fi

        commands+=("set $jail banip $ip")
        total=$((total + 1))
    done
done

if [ "$total" -eq 0 ]; then
    echo "no banned IPs found, nothing to do"
    exit 0
fi

# Bail out early and loudly if the secondary is unreachable.
# If you want literally one SSH connection total, remove this block
# and rely on the error handling around the batch SSH call below.
if ! ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" true 2>/dev/null; then
    echo "cannot reach $REMOTE_HOST, skipping this run" >&2
    exit 0
fi

# Final command for the interactive client.
commands+=("exit")

echo "syncing $total IP(s) to $REMOTE_HOST"

rc=0
printf '%s\n' "${commands[@]}" | ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "sudo fail2ban-client -i" 2>&1 || rc=$?

echo

if [ "$rc" -eq 0 ]; then
    echo "sync batch completed: $total IP(s) sent to $REMOTE_HOST"
else
    echo "sync batch to $REMOTE_HOST failed with exit code $rc" >&2
fi

exit 0