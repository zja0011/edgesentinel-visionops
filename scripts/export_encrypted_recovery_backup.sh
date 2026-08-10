#!/usr/bin/env bash
set -euo pipefail

project_dir="/home/nvidia/projects/edgesentinel-visionops"
credential_path="/etc/edgesentinel-visionops/recovery-export.key"
output_dir="/home/nvidia/edgesentinel-recovery-exports/encrypted"

cd "$project_dir"

if [ -f /.dockerenv ]; then
  echo "ERROR: run encrypted recovery export on the Jetson host." >&2
  exit 1
fi
if [ "$#" -ne 1 ]; then
  echo "Usage: bash scripts/export_encrypted_recovery_backup.sh BACKUP_ID" >&2
  exit 2
fi
backup_id="$1"
case "$backup_id" in
  dr_[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
  *) echo "ERROR: invalid backup ID." >&2; exit 2 ;;
esac

bash "$project_dir/scripts/configure_recovery_export_key.sh" status
mkdir -p -- "$output_dir"

sudo python3 -m apps.recovery_export create \
  --project-dir "$project_dir" \
  --backup-id "$backup_id" \
  --output-dir "$output_dir" \
  --key-file "$credential_path"

sudo chown nvidia:nvidia \
  "$output_dir/$backup_id.esdr" \
  "$output_dir/$backup_id.esdr.json"
chmod 600 \
  "$output_dir/$backup_id.esdr" \
  "$output_dir/$backup_id.esdr.json"

echo
echo "Encrypted recovery export prepared."
echo "Artifact: $output_dir/$backup_id.esdr"
echo "Metadata: $output_dir/$backup_id.esdr.json"
echo "Private plaintext archive persisted: False"
echo "Next: copy both files to the trusted off-device store."
