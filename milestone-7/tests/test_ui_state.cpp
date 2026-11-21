// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
#include "ui_state.hpp"
#include "../rhmiapp/controls_entry.hpp"
#include <assert.h>
#include <limits.h>

int main() {
    char record[80];
    nbt::UiState s;
    nbt::ControlsEntry controls;
    controls.begin(1000);
    const unsigned token = controls.token();
    // Favourite preview/touch must never be mistaken for menu acknowledgement.
    assert(nbt::parseUiState("connected 42 0 1 1001", s));
    assert(s.favouritePeek && s.favouriteTouchMask == 1001 && s.controlsAck == 0);
    assert(controls.poll(1100, true, false, s.controlsAck) == nbt::ControlsEntry::NONE);
    assert(nbt::formatUiState(record, sizeof(record), "connected", 42, 1, true, 7, token) > 0);
    assert(nbt::parseUiState(record, s));
    assert(s.controlsAck == token && s.favouritePeek && s.favouriteTouchMask == 7);
    assert(controls.poll(1200, true, s.overlay != 0, s.controlsAck) == nbt::ControlsEntry::NONE);
    assert(nbt::formatUiState(record, sizeof(record), "connected", 42, 0, false, 0, token) > 0);
    assert(nbt::parseUiState(record, s));
    assert(controls.poll(1300, true, s.overlay != 0, s.controlsAck) == nbt::ControlsEntry::OPEN_MENU);
    // Shorter legacy records reset optional fields, even after a full record.
    assert(nbt::parseUiState("connected 42 0", s) && s.controlsAck == 0 && !s.favouritePeek);
    assert(nbt::parseUiState("connected 42 0 1001", s) && s.controlsAck == 0);
    assert(nbt::parseUiState("idle 42", s) && s.overlay == 0 && s.favouriteTouchMask == 0);
    assert(!nbt::parseUiState("", s) && s.pid == 0 && s.controlsAck == 0);
    assert(nbt::formatUiState(record, sizeof(record), "connecting", INT_MAX, 5, true, UINT_MAX, UINT_MAX) > 0);
    assert(nbt::parseUiState(record, s) && s.controlsAck == UINT_MAX && s.favouriteTouchMask == UINT_MAX);
    assert(nbt::formatUiState(record, 8, "connected", 42, 0, false, 0, 1) == -1);
    puts("PASS: upstream status compatibility, separate controls ACK, release gating and bounded formatting");
}
