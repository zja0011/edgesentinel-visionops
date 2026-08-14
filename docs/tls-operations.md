# EdgeSentinel TLS operations

## Reboot recovery proof

The reboot marker contains only public runtime identity: boot ID, service start
time, vision frame metadata, model mode, TLS public origin, and the SHA-256 of
the public certificate. It never contains the TLS private key, model key,
password, cookie, or CSRF token.

Run the preflight on the Jetson host:

```bash
cd ~/projects/edgesentinel-visionops
bash scripts/prepare_reboot_test.sh
sudo reboot
```

After reconnecting:

```bash
cd ~/projects/edgesentinel-visionops
bash scripts/check_reboot_recovery.sh
```

When TLS is configured, both scripts automatically use the certificate-pinned
HTTPS runtime check. Recovery fails closed if the boot ID did not change, the
service did not restart, TLS was disabled, the public origin changed, or the
certificate fingerprint changed unexpectedly.

## Confirmed certificate rotation

Rotation is a host-admin operation and requires the exact phrase
`ROTATE_TLS_CERTIFICATE`. It creates a new key pair without changing the
currently running in-memory certificate, stores the previous credential in a
`root:root 0700` backup directory, and stores backup private keys as
`root:root 0600`. At most five protected backups are allowed; the script never
deletes an old backup automatically.

```bash
cd ~/projects/edgesentinel-visionops
bash scripts/rotate_tls_boot.sh
sudo systemctl restart edgesentinel-visionops.service
bash scripts/check_tls_rotation.sh
```

If generation or installation fails, the previous certificate, key,
environment file, and public export are restored. After a successful rotation,
copy the new public certificate to the Windows checkout and rerun the pinned
Dashboard check:

```powershell
scp JETSON_USER@JETSON_IP:/home/JETSON_USER/projects/edgesentinel-visionops/data/runtime/tls/edgesentinel-server.crt `
  .\data\runtime\tls\edgesentinel-server.crt
powershell -ExecutionPolicy Bypass `
  -File .\scripts\check_tls_dashboard.ps1 `
  -Username "zja"
```

The rotation acceptance check requires the host certificate, in-memory
container certificate, public export, protected audit record, and protected
backup to agree. It also proves the managed service restarted after rotation.
