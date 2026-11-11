# Channel settings portability

In Channel settings > Advanced, export the saved settings to a ZIP. Create a channel on the destination Studio and import the ZIP there. The existing destination episodes and project snapshots remain untouched.

The version 2 archive contains channel configuration, scriptwriter wishes, automation choices, branding images, host and style pictures, voice IDs and settings, translation voice IDs/defaults, translation thumbnail options, director memory, channel AGENTS.md and a snapshot of external author/montage rules. Voice reference recordings and generated audio are excluded. Save a service voice ID before exporting a configured local voice. Importing IDs starts no cloning or speech generation. Use a provider key with access to the saved voices on the destination. No project, pending job or API credential is included. Global rules on the destination are not overwritten.

Before replacement the Studio saves the previous configuration locally, including its existing voice files. Older version 1 archives remain readable. Advanced lists backup dates and disk usage, with restore and deletion controls. Restore saves the current configuration as a new backup first. Imported settings become defaults for future work; existing projects and audio stay intact.

## Local API

- `GET /api/channels/{cid}/settings-export`: ZIP attachment.
- `POST /api/channels/{cid}/settings-import`: raw ZIP body, `Content-Type: application/zip`.
- `GET /api/channels/{cid}/settings-backups`: backup IDs, dates and sizes.
- `POST /api/channels/{cid}/settings-backups/{id}/restore`: restore settings, JSON `{}`.
- `DELETE /api/channels/{cid}/settings-backups/{id}`: delete one backup.

Import/export are blocked while the channel is producing content. Bundles are versioned, limited to 128 MiB expanded and 512 payload files, and validated before mutation. Only known logical file paths are accepted. Checksums, sizes, duplicate entries, symlinks, encryption and traversal are checked. Source audio mtimes are retained because existing voice clone metadata relies on them. File replacement rolls back on failure. Backups live under `DATA_ROOT/channel-settings-backups/{cid}` and never enter exported ZIPs.
