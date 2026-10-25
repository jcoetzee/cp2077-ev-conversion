"""Generic read-only walker for CR2W (v195) exports, used to inspect audio metadata.

Property encoding: name idx u16, type idx u16, size u32 (includes itself), value.
Struct values: 0x00, properties..., terminated by name idx 0 (u16 0x0000).
"""
import struct

SIMPLE = {
    "Bool": "<?", "Uint8": "<B", "Int8": "<b", "Uint16": "<H", "Int16": "<h",
    "Uint32": "<I", "Int32": "<i", "Uint64": "<Q", "Int64": "<q", "Float": "<f", "Double": "<d",
}


class CR2W:
    def __init__(self, data: bytes):
        self.d = data
        tables = [struct.unpack_from("<III", data, 40 + i * 12) for i in range(10)]
        s_off, s_size, _ = tables[0]
        self.strings = data[s_off : s_off + s_size]
        n_off, n_cnt, _ = tables[1]
        self.names = []
        for i in range(n_cnt):
            o, _h = struct.unpack_from("<II", data, n_off + i * 8)
            self.names.append(self.strings[o : self.strings.index(b"\0", o)].decode(errors="replace"))
        self.name_index = {n: i for i, n in enumerate(self.names)}
        e_off, e_cnt, _ = tables[4]
        self.exports = [struct.unpack_from("<HHIIIII", data, e_off + i * 24) for i in range(e_cnt)]

    def export_class(self, i):
        return self.names[self.exports[i][0]]

    def export_props(self, i):
        _cls, _f, _p, size, off, _t, _c = self.exports[i]
        return self.read_struct(off + 1, off + size)

    def read_struct(self, pos, end):
        """Returns list of (name, type, value_offset, value_size)."""
        props = []
        while pos + 2 <= end:
            (name_idx,) = struct.unpack_from("<H", self.d, pos)
            if name_idx == 0:
                break
            type_idx, size = struct.unpack_from("<HI", self.d, pos + 2)
            props.append((self.names[name_idx], self.names[type_idx], pos + 8, size - 4))
            pos += 4 + size
        return props

    def value(self, typ, off, size, depth=0, max_depth=6):
        d = self.d
        if typ in SIMPLE:
            return struct.unpack_from(SIMPLE[typ], d, off)[0]
        if typ == "CName":
            return self.names[struct.unpack_from("<H", d, off)[0]]
        if typ.startswith("handle:") or typ.startswith("whandle:"):
            return ("handle", struct.unpack_from("<i", d, off)[0])
        if typ.startswith("array:"):
            inner = typ[6:]
            (count,) = struct.unpack_from("<I", d, off)
            if inner == "CName":
                return [self.names[struct.unpack_from("<H", d, off + 4 + 2 * k)[0]] for k in range(count)]
            if inner.startswith("handle:"):
                return [("handle", struct.unpack_from("<i", d, off + 4 + 4 * k)[0]) for k in range(count)]
            if depth >= max_depth:
                return f"<array {inner} x{count}>"
            out, pos = [], off + 4
            for _ in range(count):
                if inner in SIMPLE:
                    out.append(struct.unpack_from(SIMPLE[inner], d, pos)[0])
                    pos += struct.calcsize(SIMPLE[inner])
                    continue
                if d[pos] != 0:
                    return out + [f"<unparsed {inner}>"]
                props = self.read_struct(pos + 1, off + size)
                out.append({n: self.value(t, o, s, depth + 1) for n, t, o, s in props})
                last = props[-1] if props else None
                pos = (last[2] + last[3] if last else pos + 1) + 2
            return out
        if size >= 1 and d[off] == 0:  # struct
            if depth >= max_depth:
                return f"<struct {typ}>"
            props = self.read_struct(off + 1, off + size)
            return {n: self.value(t, o, s, depth + 1) for n, t, o, s in props}
        return f"<{typ} {size}b>"
