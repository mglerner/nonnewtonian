# Encrypted off-site backups (M7)

This makes the privacy-page line "encrypted backups kept off-site" actually
true. It backs up a consistent SQLite snapshot + the photos directory to a
[restic](https://restic.net) repository on Backblaze B2, nightly, via a systemd
timer, and gives you a one-command restore test.

**Every command below is for you to run on the server.** Claude wrote these
files but does not and will not connect to your server or run anything on it.

The one real footgun this avoids: the live `app.db` is in WAL mode, so a plain
file copy can grab a torn, half-written database. `nnp-backup.sh` takes a
consistent snapshot with sqlite's `.backup` API and integrity-checks it before
and after, so a bad copy fails loudly instead of silently.

## Files here

| file                     | goes to                                                   |
| ------------------------ | --------------------------------------------------------- |
| `nnp-backup.sh`          | stays in the repo checkout (or `/opt/nnp/deploy/backup/`) |
| `nnp-restore-test.sh`    | same                                                      |
| `nnp-backup.env.example` | copy to `/etc/nnp-backup.env`                             |
| `nnp-backup.service`     | copy to `/etc/systemd/system/`                            |
| `nnp-backup.timer`       | copy to `/etc/systemd/system/`                            |

## One-time setup (on the server)

1. **Install the tools:**
   ```
   sudo apt update && sudo apt install -y restic sqlite3
   ```

2. **Create the off-site target.** In the Backblaze web console: make a
   *private* B2 bucket, then an application key scoped to it. Note the bucket
   name, the `keyID`, and the `applicationKey`.

3. **Pick the encryption passphrase and save it in your password manager first**
   (it is the only key to the backups). Then put it on the server root-only:
   ```
   sudo mkdir -p /etc/nnp-backup
   printf '%s' 'YOUR-LONG-RANDOM-PASSPHRASE' | sudo tee /etc/nnp-backup/restic-pass >/dev/null
   sudo chmod 600 /etc/nnp-backup/restic-pass
   ```

4. **Write the config:**
   ```
   sudo cp deploy/backup/nnp-backup.env.example /etc/nnp-backup.env
   sudo nano /etc/nnp-backup.env        # set NNP_DB, NNP_PHOTOS, bucket, B2 keys
   sudo chmod 600 /etc/nnp-backup.env
   ```

5. **Initialise the restic repo** (once). Load the config into the shell, then init:
   ```
   set -a; . /etc/nnp-backup.env; set +a
   restic init
   ```

6. **Install and enable the timer:**
   ```
   sudo cp deploy/backup/nnp-backup.{service,timer} /etc/systemd/system/
   sudo nano /etc/systemd/system/nnp-backup.service   # fix ExecStart path if not /opt/nnp/...
   sudo systemctl daemon-reload
   sudo systemctl enable --now nnp-backup.timer
   ```

## Verify (do this before trusting it)

7. **Run one backup now and read the log:**
   ```
   sudo systemctl start nnp-backup.service
   journalctl -u nnp-backup.service -n 40 --no-pager
   ```

8. **Test a restore** -- an untested backup is not a backup:
   ```
   set -a; . /etc/nnp-backup.env; set +a
   ./deploy/backup/nnp-restore-test.sh
   ```
   It should print `restore OK: integrity ok, N entries ...`.

9. Check the schedule: `systemctl list-timers nnp-backup.timer`.

**Only after step 8 passes is the privacy page's "encrypted backups kept
off-site" line true.** Until then, don't publish that page (or soften the line).

## Restoring for real

```
set -a; . /etc/nnp-backup.env; set +a
restic snapshots                       # find the one you want
restic restore latest --target /tmp/restore
# then stop the app, copy /tmp/restore/.../app.db + photos into place, restart
```
