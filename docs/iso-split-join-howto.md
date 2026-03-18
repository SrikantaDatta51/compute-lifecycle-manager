# ISO Split & Join — How-To Guide

Transfer large ISO files (or any large file) across unreliable uploads, FAT32 USB drives, or bandwidth-limited links. The scripts split on the source machine, validate every chunk with SHA-256 checksums, and reassemble + verify on the destination.

## Why This Exists

| Problem | Solution |
|---|---|
| Upload fails on large ISOs (>4 GB) | Split into smaller chunks, transfer individually |
| FAT32 USB max file size is 4 GB | Default chunk size is ~4 GB (FAT32-safe) |
| Silent corruption during copy | SHA-256 checksums for each chunk **and** the final file |
| Partial transfers / missing chunks | Manifest tracks expected chunk count |
| Need to retry failed pieces | Re-copy only the failed chunk, re-verify |

## Quick Start

### On Source (macOS / any machine)

```bash
# Split a 20 GB ISO into ~4 GB chunks (default)
./scripts/iso-split-join/iso-split.sh /path/to/big-image.iso

# Split into 2 GB chunks
./scripts/iso-split-join/iso-split.sh /path/to/big-image.iso 2g

# Split into 1 GB chunks to a specific output dir
./scripts/iso-split-join/iso-split.sh /path/to/big-image.iso 1g /tmp/my-split
```

### Transfer

```bash
# Option A: Compress first, then copy
tar czf big-image-split.tar.gz -C big-image-split .
scp big-image-split.tar.gz user@dest:/tmp/

# Option B: rsync the directory directly (supports resume)
rsync -avP big-image-split/ user@dest:/tmp/big-image-split/

# Option C: Copy to USB drive
cp -r big-image-split/ /Volumes/USB_DRIVE/
```

### On Destination (Linux / any machine)

```bash
# If you tar'd it, extract first
mkdir big-image-split && tar xzf big-image-split.tar.gz -C big-image-split

# Join and verify (all 5 integrity checks run automatically)
./iso-join.sh /tmp/big-image-split/

# Join to a specific output path
./iso-join.sh /tmp/big-image-split/ /data/images/big-image.iso
```

## Output Structure

After splitting, the output directory looks like:

```
big-image-split/
├── chunks/
│   ├── part-aa           # 4 GB chunk
│   ├── part-ab           # 4 GB chunk
│   ├── part-ac           # 4 GB chunk
│   ├── part-ad           # 4 GB chunk
│   └── part-ae           # remainder
├── chunk-checksums.sha256    # SHA-256 for each chunk
├── original-checksum.sha256  # SHA-256 of the complete original file
└── manifest.txt              # metadata (filename, size, chunk count, etc.)
```

## Verification Steps (iso-join.sh)

The join script runs **5 sequential integrity checks**:

| Step | Check | Catches |
|------|-------|---------|
| 1 | Chunk count matches manifest | Missing/extra files from incomplete copy |
| 2 | Per-chunk SHA-256 verification | Bit-rot, corruption during transfer |
| 3 | Concatenation | — |
| 4 | File size matches original | Truncation, extra data |
| 5 | Whole-file SHA-256 matches original | Any corruption whatsoever |

If **any** check fails, the script reports exactly which chunk or step failed so you can re-copy only what's needed.

## Common Scenarios

### Scenario 1: Upload keeps failing at 60%

```bash
# On Mac: split into 1 GB chunks
./iso-split.sh bcm-11.0.iso 1g

# Upload chunks individually (retry whichever fails)
for f in bcm-11.0-split/chunks/part-*; do
    scp "$f" user@dest:/tmp/bcm-11.0-split/chunks/ || echo "RETRY: $f"
done

# Also copy the metadata files
scp bcm-11.0-split/*.sha256 bcm-11.0-split/manifest.txt user@dest:/tmp/bcm-11.0-split/

# On dest: join & verify
./iso-join.sh /tmp/bcm-11.0-split/
```

### Scenario 2: USB drive is FAT32 (4 GB file size limit)

```bash
# Default 4000m chunk size is already FAT32-safe
./iso-split.sh giant.iso

# Copy to USB
cp -r giant-split/ /Volumes/USBDRIVE/

# On destination, plug in USB and join
./iso-join.sh /mnt/usb/giant-split/
```

### Scenario 3: One chunk failed verification

```bash
# The join script will tell you exactly which chunk failed, e.g.:
#   [FAIL] Chunk part-ac: CHECKSUM MISMATCH

# Re-copy just that chunk from source
scp user@source:/tmp/bcm-split/chunks/part-ac /tmp/bcm-split/chunks/

# Re-run join
./iso-join.sh /tmp/bcm-split/
```

## Requirements

| Tool | macOS | Linux |
|------|-------|-------|
| `split` | Built-in | Built-in (coreutils) |
| `cat` | Built-in | Built-in |
| `shasum -a 256` | Built-in | — |
| `sha256sum` | — | Built-in (coreutils) |
| `bash` ≥ 4.x | Built-in | Built-in |

Both scripts auto-detect which SHA-256 tool is available. No additional packages needed.

## Integration with BCM Workflows

These scripts are useful for transferring BCM software images between environments:

```bash
# Example: Split BCM 11.0 ISO for transfer to air-gapped cluster
./scripts/iso-split-join/iso-split.sh /images/bcm-11.0-release.iso 2g

# Transfer to head node, then join
./scripts/iso-split-join/iso-join.sh /data/bcm-11.0-release-split/ /data/images/bcm-11.0-release.iso
```
