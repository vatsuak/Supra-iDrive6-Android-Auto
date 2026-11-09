// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD (https://github.com/Sq00ky/Supra-iDrive6-Android-Auto)
#ifndef NBT_CONNECTION_PROMPT_HPP
#define NBT_CONNECTION_PROMPT_HPP

#include <stdint.h>

namespace nbt {

// Pure policy: unknown telemetry never counts as a disconnect. Only a confirmed,
// sustained disconnect rearms a dismissed/expired prompt. Times are monotonic ms.
class ConnectionPrompt {
public:
    enum Effect { NONE, SHOW, HIDE };
    enum { CONNECT_MS = 2000, DISCONNECT_MS = 5000, TIMEOUT_MS = 20000 };
    ConnectionPrompt() { reset(); }

    void reset() {
        visible_ = consumed_ = connecting_ = disconnecting_ = manual_ = false;
        since_ = shown_ = 0;
    }
    bool visible() const { return visible_; }
    bool manual() const { return manual_; }
    bool test(uint32_t now, bool blocked, bool running) {
        if (blocked || running || visible_) return false;
        visible_ = manual_ = true;
        shown_ = now;
        return true;
    }
    void dismiss() { visible_ = manual_ = false; consumed_ = true; }

    Effect poll(uint32_t now, bool enabled, bool known, bool connected,
                bool blocked, bool running) {
        if (!known) { connecting_ = disconnecting_ = false; }
        else if (!connected) {
            connecting_ = false;
            if (!disconnecting_) { disconnecting_ = true; since_ = now; }
            if ((uint32_t)(now - since_) >= DISCONNECT_MS) consumed_ = false;
        } else {
            disconnecting_ = false;
            if (!connecting_) { connecting_ = true; since_ = now; }
        }
        if (visible_) {
            if (blocked || running || (!manual_ && (!enabled || !known || !connected)) ||
                (uint32_t)(now - shown_) >= TIMEOUT_MS) {
                dismiss();
                return HIDE;
            }
            return NONE;
        }
        if (!enabled || !known || !connected || blocked || running || consumed_ ||
            !connecting_ || (uint32_t)(now - since_) < CONNECT_MS) return NONE;
        visible_ = consumed_ = true;
        manual_ = false;
        shown_ = now;
        return SHOW;
    }

private:
    bool visible_, consumed_, connecting_, disconnecting_, manual_;
    uint32_t since_, shown_;
};

} // namespace nbt
#endif
