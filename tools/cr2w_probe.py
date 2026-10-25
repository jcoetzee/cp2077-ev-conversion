"""Probe a CR2W file's header/tables and test which byte ranges its CRCs cover."""
import struct
import sys
import zlib

data = open(sys.argv[1], "rb").read()
magic, ver, flags, ts, build, obj_end, buf_end, hcrc, nchunks = struct.unpack_from("<4sIIQIIIII", data, 0)
print(f"version={ver} flags={flags} build={build} objectsEnd={obj_end} buffersEnd={buf_end} "
      f"headerCRC={hcrc:08x} chunks={nchunks} filesize={len(data)}")
tables = [struct.unpack_from("<III", data, 40 + i * 12) for i in range(10)]
names = ["strings", "names", "imports", "properties", "exports", "buffers", "embeds", "t7", "t8", "t9"]
for n, (off, cnt, crc) in zip(names, tables):
    if off:
        print(f"  {n:10} off=0x{off:x} count={cnt} crc={crc:08x}")

entry_size = {"strings": 1, "names": 8, "imports": 8, "properties": 16, "exports": 24, "buffers": 24, "embeds": 24}
for n, (off, cnt, crc) in zip(names, tables):
    if not off:
        continue
    blob = data[off : off + cnt * entry_size.get(n, 1)]
    print(f"  {n:10} crc32(table bytes)={zlib.crc32(blob):08x} {'MATCH' if zlib.crc32(blob) == crc else ''}")

# header CRC: try header(with crc zeroed)+table descriptors
hdr = bytearray(data[:160])
struct.pack_into("<I", hdr, 0x20, 0)
print(f"  crc32(header 0..160, crc zeroed) = {zlib.crc32(bytes(hdr)):08x} "
      f"{'MATCH' if zlib.crc32(bytes(hdr)) == hcrc else ''}")
off, cnt, _ = tables[4]
for i in range(cnt):
    cls, oflags, parent, size, doff, tmpl, ecrc = struct.unpack_from("<HHIIIII", data, off + i * 24)
    print(f"  export {i}: class={cls} size={size} dataOffset=0x{doff:x} crc={ecrc:08x}")
