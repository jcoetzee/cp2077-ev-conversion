// Portable replacement for ooz's Windows-only stdafx.h (macOS / Apple Silicon).
#pragma once

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <assert.h>

#if defined(__aarch64__) || defined(__arm64__)
#include "../ooz/sse2neon.h"
#else
#include <immintrin.h>
#endif

typedef unsigned char byte;
typedef unsigned char uint8;
typedef unsigned int uint32;
typedef uint64_t uint64;
typedef int64_t int64;
typedef signed int int32;
typedef unsigned short uint16;
typedef signed short int16;
typedef unsigned int uint;

#define __forceinline inline __attribute__((always_inline))

static inline unsigned char _BitScanReverse(unsigned long *index, uint32_t mask) {
  if (!mask) return 0;
  *index = 31 - __builtin_clz(mask);
  return 1;
}
static inline unsigned char _BitScanForward(unsigned long *index, uint32_t mask) {
  if (!mask) return 0;
  *index = __builtin_ctz(mask);
  return 1;
}
static inline uint32_t _rotl(uint32_t v, int n) {
  n &= 31;
  return n ? (v << n) | (v >> (32 - n)) : v;
}
#define _byteswap_ushort(x) __builtin_bswap16(x)
#define _byteswap_ulong(x) __builtin_bswap32(x)
#define _byteswap_uint64(x) __builtin_bswap64(x)
