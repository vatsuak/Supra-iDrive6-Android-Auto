// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD (https://github.com/Sq00ky/Supra-iDrive6-Android-Auto)
#ifndef NBT_PHONE_WATCH_STATE_HPP
#define NBT_PHONE_WATCH_STATE_HPP

#include <stdint.h>
#include <stdio.h>

namespace nbt {
struct PhoneWatchState {
    bool known, connected;
    PhoneWatchState() : known(false), connected(false) {}
    // Bind every sample to our spawned child and reject stale/partial records.
    // A dead watcher or a leftover file never becomes a connection notification.
    bool parse(const char* text, int childPid, uint32_t now) {
        known = connected = false;
        unsigned pid = 0, stamp = 0, k = 0, c = 0;
        char extra = 0;
        if (!text || childPid <= 0 || sscanf(text, "v1 %u %u %u %u %c", &pid, &stamp, &k, &c, &extra) != 4 ||
            pid != (unsigned)childPid || (uint32_t)(now - stamp) > 3000u || k > 1 || c > 1 || (!k && c)) return false;
        known = k != 0; connected = c != 0;
        return true;
    }
};
} // namespace nbt
#endif
