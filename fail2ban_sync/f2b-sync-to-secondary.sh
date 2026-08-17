#!/bin/bash
#
# f2b-sync-to-secondary.sh
#
# Pushes currently-banned IPs from this host's fail2ban jails to a
# secondary fail2ban instance over SSH, using `fail2ban-client set
# <jail> banip <ip>`. Idempotent — re-banning an already-banned IP
# is a harmless no-op. Intended to run periodically via systemd timer.
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
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=5"

# Leave empty to sync all jails, or set an explicit space-separated
# list to only sync specific ones, e.g. JAILS="sshd nginx-proxy"
JAILS="${F2B_SYNC_JAILS:-}"

if [ -z "$JAILS" ]; then
    JAILS=$(sudo fail2ban-client status | awk -F'\t' '/Jail list/ {print $2}' | tr ',' ' ')
fi

if [ -z "$JAILS" ]; then
    echo "no jails found, nothing to do"
    exit 0
fi

# Bail out early and loudly if the secondary is unreachable, rather
# than silently failing on every individual ban push.
if ! ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" true 2>/dev/null; then
    echo "cannot reach $REMOTE_HOST, skipping this run" >&2
    exit 0
fi

total=0
failed=0

for jail in $JAILS; do
    ips=$(sudo fail2ban-client status "$jail" 2>/dev/null \
          | awk -F':' '/Banned IP list/ {print $2}')

    for ip in $ips; do
        [ -z "$ip" ] && continue
        total=$((total + 1))
        if ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" \
              "sudo fail2ban-client set $jail banip $ip" >/dev/null 2>&1; then
            echo "banned $ip in $jail on $REMOTE_HOST"
        else
            failed=$((failed + 1))
            echo "failed to ban $ip in $jail on $REMOTE_HOST" >&2
        fi
    done
done

echo "sync complete: $total IP(s) processed, $failed failed against $REMOTE_HOST"
