/* Exercise the production CRC guard against actual official release files. */
#include <stdio.h>
static const char* baseline;
#define AA_TILE_DAEMON_FILE baseline
#define main helper_main
#include "../../milestone-7/tools/aa_tile.c"
#undef main
int main(int argc, char** argv) {
    if (argc != 3) return 2;
    baseline = argv[1];
    if (baselineVerified() != atoi(argv[2])) return 1;
    puts("PASS: actual release fixture matches expected acceptance");
    return 0;
}
