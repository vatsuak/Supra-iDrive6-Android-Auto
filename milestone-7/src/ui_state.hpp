// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
#ifndef NBT_UI_STATE_HPP
#define NBT_UI_STATE_HPP
#include <stdio.h>
#include <string.h>

namespace nbt {
// Append-only status record shared by the daemon and PluginApp.
// Upstream fields 1..5: state pid overlay favouritePeek favouriteTouchMask.
// options3 adds controlsAck at field 6. Old options2's fourth-field ACK is
// deliberately not accepted: mixed binaries must not acknowledge a menu visit.
struct UiState {
    char state[24];
    int pid, overlay;
    bool favouritePeek;
    unsigned favouriteTouchMask, controlsAck;
    UiState() : pid(0), overlay(0), favouritePeek(false),
                favouriteTouchMask(0), controlsAck(0) { strcpy(state, "idle"); }
};

inline bool parseUiState(const char* record, UiState& out) {
    out = UiState();
    UiState parsed;
    int favourite = 0;
    const int n = sscanf(record, "%23s %d %d %d %u %u", parsed.state,
                         &parsed.pid, &parsed.overlay, &favourite,
                         &parsed.favouriteTouchMask, &parsed.controlsAck);
    if (n < 2) return false;
    parsed.favouritePeek = n >= 4 && favourite == 1;
    out = parsed;
    return true;
}

inline int formatUiState(char* record, size_t size, const char* state, int pid,
                         int overlay, bool favouritePeek, unsigned touchMask,
                         unsigned controlsAck) {
    const int n = snprintf(record, size, "%-11.11s %10d %d %d %u %10u\n",
                           state ? state : "idle", pid, overlay,
                           favouritePeek ? 1 : 0, touchMask, controlsAck);
    return n < 0 || (size_t)n >= size ? -1 : n;
}
}
#endif
