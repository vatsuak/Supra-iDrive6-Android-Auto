// Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD
#ifndef NBT_TILE_POLICY_HPP
#define NBT_TILE_POLICY_HPP
namespace nbt {
// One attempt per daemon/enable cycle. A failed helper never loops on its own.
// Lock contention is not an attempt: wait for the retiring helper to clean up.
struct TilePolicy {
    int attemptedPid;
    TilePolicy() : attemptedPid(0) {}
    bool launch(bool enabled, int pid, bool connected, bool locked) {
        if (!enabled) { attemptedPid = 0; return false; }
        if (pid <= 0 || !connected || locked || attemptedPid == pid) return false;
        attemptedPid = pid;
        return true;
    }
};
}
#endif
