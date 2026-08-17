# fail2ban primary → secondary ban sync

Pushes currently-banned IPs from `pihole1` (primary) to `pihole2`
(secondary) every 5 minutes via `fail2ban-client set <jail> banip <ip>`,
run over the existing passwordless SSH trust from the `pi` user on
pihole1 → pihole2, using `sudo` on the remote end for the actual
fail2ban command. No new accounts or sudoers rules needed as long as
`pi` still has passwordless sudo on pihole2 (the Raspberry Pi OS
default).

## Before installing: confirm pi has passwordless sudo on pihole2

```bash
ssh pi@pihole2 sudo -n fail2ban-client status
```

If that prints jail status without prompting for a password, you're
set. If it prompts or errors, either restore pi's default NOPASSWD
sudoers entry or add a narrow one just for this:

```bash
echo 'pi ALL=(root) NOPASSWD: /usr/bin/fail2ban-client set * banip *' \
  | sudo tee /etc/sudoers.d/f2b-sync
sudo chmod 440 /etc/sudoers.d/f2b-sync
```

## Install (on pihole1)

```bash
sudo install -m 755 f2b-sync-to-secondary.sh /usr/local/bin/f2b-sync-to-secondary.sh
sudo install -m 644 f2b-sync.service /etc/systemd/system/f2b-sync.service
sudo install -m 644 f2b-sync.timer   /etc/systemd/system/f2b-sync.timer

sudo systemctl daemon-reload
sudo systemctl enable --now f2b-sync.timer
```

## Verify

```bash
sudo systemctl list-timers f2b-sync.timer
sudo systemctl start f2b-sync.service   # trigger one run manually
journalctl -t f2b-sync -f
```

## Notes

- To limit syncing to specific jails instead of all of them, set
  `Environment=F2B_SYNC_JAILS="sshd nginx-proxy"` under `[Service]`
  in `f2b-sync.service`.
- Bans pushed this way pick up the secondary jail's own configured
  `bantime`, not the primary's remaining ban time — for closing the
  gap during a reboot window that's the safer direction to round.
- The script exits quietly (logging via `logger -t f2b-sync`) if
  `pihole2` is unreachable, so a normal reboot won't spam failures —
  check with `journalctl -t f2b-sync`.
- Runs independently of `copy-pihole-config` — that script syncs
  config files and restarts fail2ban on pihole2; this timer pushes
  live ban state between the two already-running instances. If
  `copy-pihole-config` restarts fail2ban on pihole2 in between timer
  runs, any bans pushed since the last config sync are cleared along
  with that restart and get reapplied on the next 5-minute run.
