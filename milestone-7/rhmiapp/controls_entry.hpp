// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
#ifndef NBT_CONTROLS_ENTRY_HPP
#define NBT_CONTROLS_ENTRY_HPP
#include <stdint.h>
namespace nbt {
// An intentional controls visit must release projection before navigating.
// The echoed token prevents a stale overlay=0 record from acknowledging it.
class ControlsEntry {
    bool pending_;
    uint32_t started_, sent_;
    unsigned token_;
public:
    enum Action { NONE, SEND, OPEN_MENU, FAILED };
    ControlsEntry() : pending_(false), started_(0), sent_(0), token_(0) {}
    void begin(uint32_t now) {
        pending_ = true; started_ = sent_ = now;
        token_ = (now & 0x7fffffffu) | 1u;
    }
    bool pending() const { return pending_; }
    unsigned token() const { return token_; }
    void cancel() { pending_ = false; }
    Action poll(uint32_t now, bool running, bool overlay, unsigned ack) {
        if (!pending_) return NONE;
        if (!running || (!overlay && ack == token_)) {
            pending_ = false; return OPEN_MENU;
        }
        if (uint32_t(now - started_) >= 5000u) {
            pending_ = false; return FAILED;
        }
        if (uint32_t(now - sent_) >= 500u) { sent_ = now; return SEND; }
        return NONE;
    }
};
}
#endif
