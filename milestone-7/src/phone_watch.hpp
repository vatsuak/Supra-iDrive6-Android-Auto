// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD (https://github.com/Sq00ky/Supra-iDrive6-Android-Auto)
#ifndef NBT_PHONE_WATCH_HPP
#define NBT_PHONE_WATCH_HPP

#include "dsi_client.hpp"
#include "gap_parse.hpp"
#include <pthread.h>
#include <ctype.h>

namespace nbt {

// Explicit selection avoids guessing Android compatibility from a Bluetooth name
// or prompting for an iPhone when two phones are paired. Accept normal MAC format.
inline bool normalizePhoneAddress(const char* input, char (&out)[18]) {
    if (!input) return false;
    for (unsigned i = 0; i < 17; ++i) {
        unsigned char ch = (unsigned char)input[i];
        if (!ch || ((i % 3 == 2) ? ch != ':' : !isxdigit(ch))) return false;
        out[i] = (char)toupper(ch);
    }
    out[17] = 0;
    return input[17] == 0;
}

// A read-only GAP observer. No SPP registration, service connection, firewall,
// audio, video or CarPlay state changes. Callbacks run on DsiClient's thread.
class PhoneWatch {
public:
    explicit PhoneWatch(const char* address);
    ~PhoneWatch();
    bool start();
    void snapshot(bool& known, bool& connected);

private:
    DsiClient client_;
    char address_[18];
    pthread_mutex_t mutex_;
    bool valid_, known_, connected_;
    void publish(bool known, bool connected);
    static void attached(DsiClient*, void*);
    static void detached(DsiClient*, void*);
    static void data(DsiClient*, uint32_t, uint32_t, uint32_t, const uint8_t*, uint32_t, void*);
    PhoneWatch(const PhoneWatch&);
    PhoneWatch& operator=(const PhoneWatch&);
};

} // namespace nbt
#endif
