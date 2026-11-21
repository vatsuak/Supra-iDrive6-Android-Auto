/* Standalone UCL adapter. SPDX-License-Identifier: GPL-2.0-or-later */
#include <ucl/ucl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#define LIMIT (64u * 1024u * 1024u)
int main(int argc, char **argv) {
    FILE *f; long size; unsigned char *src, *dst;
    ucl_uint output_size; int rc, compress; unsigned long expected = 0; char *end;
    if (argc < 4 || argc > 5) return 2;
    compress = !strcmp(argv[1], "compress");
    if ((!compress && strcmp(argv[1], "decompress")) || (compress ? argc != 4 : argc != 5)) return 2;
    if (!compress) {
        errno = 0; expected = strtoul(argv[4], &end, 10);
        if (errno || !argv[4][0] || *end || expected > LIMIT) return 2;
    }
    if (ucl_init() != UCL_E_OK) { fputs("UCL init failed\n", stderr); return 3; }
    f = fopen(argv[2], "rb"); if (!f) return 4;
    if (fseek(f, 0, SEEK_END) || (size = ftell(f)) < 0 || size > LIMIT || fseek(f, 0, SEEK_SET)) { fclose(f); return 4; }
    src = (unsigned char*)malloc(size ? (size_t)size : 1);
    output_size = compress ? (ucl_uint)size + (ucl_uint)size / 8 + 256 : (ucl_uint)expected;
    dst = (unsigned char*)malloc(output_size ? output_size : 1);
    if (!src || !dst) { fclose(f); free(src); free(dst); return 5; }
    if (fread(src, 1, size, f) != (size_t)size) { fclose(f); free(src); free(dst); return 4; }
    fclose(f);
    if (compress) rc = ucl_nrv2d_99_compress(src, (ucl_uint)size, dst, &output_size, NULL, 10, NULL, NULL);
    else rc = ucl_nrv2d_decompress_safe_8(src, (ucl_uint)size, dst, &output_size, NULL);
    free(src);
    if (rc != UCL_E_OK || (!compress && output_size != expected)) {
        fprintf(stderr, "UCL result %d; size %lu\n", rc, (unsigned long)output_size); free(dst); return 6;
    }
    f = fopen(argv[3], "wb"); if (!f) { free(dst); return 4; }
    if (fwrite(dst, 1, output_size, f) != output_size) { fclose(f); free(dst); return 4; }
    free(dst); return fclose(f) ? 4 : 0;
}
