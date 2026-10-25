#!/bin/sh
# Builds libooz.dylib (Kraken decompressor only) for macOS / Apple Silicon from upstream
# ooz (GPLv3, https://github.com/powzix/ooz). Upstream sources are fetched at a pinned
# commit and are not stored in this repository.
set -e
cd "$(dirname "$0")"

OOZ_DIR=../ooz
OOZ_COMMIT=05038060aa68f9187ae9923b2388ca8db40e58d1
SSE2NEON_URL=https://raw.githubusercontent.com/DLTcollab/sse2neon/master/sse2neon.h

if [ ! -d "$OOZ_DIR/.git" ]; then
  git clone https://github.com/powzix/ooz.git "$OOZ_DIR"
fi
git -C "$OOZ_DIR" checkout -q "$OOZ_COMMIT"
if [ ! -f "$OOZ_DIR/sse2neon.h" ]; then
  curl -sSfL -o "$OOZ_DIR/sse2neon.h" "$SSE2NEON_URL"
fi

# Library part of kraken.cpp only: stops before the CLI/test harness and Windows DLL loader.
sed -n '1,4162p' "$OOZ_DIR/kraken.cpp" > kraken_lib.cpp
cat >> kraken_lib.cpp <<'EOF'

extern "C" int ooz_kraken_decompress(const unsigned char *src, size_t src_len,
                                     unsigned char *dst, size_t dst_len) {
  return Kraken_Decompress(src, src_len, dst, dst_len);
}
EOF
cp "$OOZ_DIR/lzna.cpp" "$OOZ_DIR/bitknit.cpp" .
clang++ -std=c++14 -O2 -fPIC -shared -w -I. kraken_lib.cpp lzna.cpp bitknit.cpp -o libooz.dylib
echo built "$(pwd)/libooz.dylib"
