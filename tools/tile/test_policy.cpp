#include "../../milestone-7/rhmiapp/tile_policy.hpp"
#include <cassert>
#include <cstdio>
int main() {
    nbt::TilePolicy p;
    assert(!p.launch(false, 12, true, false));
    assert(!p.launch(true, 12, false, false));
    assert(!p.launch(true, 12, true, true));
    assert(p.launch(true, 12, true, false));
    assert(!p.launch(true, 12, true, false)); // Failed spawn/crash cannot loop.
    assert(!p.launch(true, -1, false, false));
    assert(!p.launch(true, 12, true, false)); // Transient missing state is no retry.
    assert(!p.launch(true, 12, false, false));
    assert(!p.launch(true, 12, true, false)); // Reconnect uses the existing helper.
    assert(p.launch(true, 13, true, false)); // New daemon gets its own attempt.
    assert(!p.launch(false, 13, true, false));
    assert(!p.launch(true, 13, true, true)); // Old helper still cleaning up.
    assert(p.launch(true, 13, true, false)); // Explicit off/on retries.
    puts("PASS: disabled default, connection gating, restart, retiring lock and no crash loop");
}
