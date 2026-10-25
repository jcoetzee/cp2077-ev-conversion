"""Find archive files whose (decompressed) content contains a byte string.

Usage: python3 tools/find_in_archives.py <needle> [archive name glob]
Searches the Mac game archives in parallel; prints archive, file hash and size of matches.
"""
import fnmatch
import glob
import multiprocessing as mp
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rdar  # noqa: E402

CONTENT = "/Applications/Cyberpunk 2077/archive/Mac"


def scan(args):
    arc, hashes, needle = args
    _v, files, segs = rdar.read_index(arc)
    hits = []
    with open(arc, "rb") as f:
        for h in hashes:
            s0, s1, _n = files[h]
            off, zs, size = segs[s0]
            if size > 4_000_000:
                continue
            f.seek(off)
            data = f.read(zs)
            try:
                raw = rdar.decompress_segment(data, size)
            except Exception:
                continue
            if needle in raw:
                hits.append((os.path.basename(arc), h, size))
    return hits


def main():
    needle = sys.argv[1].encode()
    pattern = sys.argv[2] if len(sys.argv) > 2 else "*.archive"
    archives = sorted(a for a in glob.glob(f"{CONTENT}/**/*.archive", recursive=True)
                      if fnmatch.fnmatch(os.path.basename(a), pattern))
    jobs = []
    for arc in archives:
        _v, files, _s = rdar.read_index(arc)
        hs = list(files)
        for i in range(0, len(hs), 2000):
            jobs.append((arc, hs[i : i + 2000], needle))
    with mp.get_context("spawn").Pool(os.cpu_count()) as pool:
        for hits in pool.imap_unordered(scan, jobs):
            for a, h, size in hits:
                print(f"{a}  {h:016x}  {size} bytes", flush=True)


if __name__ == "__main__":
    main()
