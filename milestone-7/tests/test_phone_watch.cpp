// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
#include "../src/phone_watch.hpp"
#include "fake_dsi_client.hpp"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static std::vector<uint8_t> devices(bool connected, bool response = true, uint32_t error = 0,
                                     const char* selected = "AA:BB:CC:DD:EE:FF") {
    std::vector<uint8_t> b;
    if (response) nbt::DsiClient::putU32(b, error);
    nbt::DsiClient::putU32(b, 2);
    nbt::DsiClient::putString(b, "Selected Android");
    nbt::DsiClient::putString(b, "Other phone");
    nbt::DsiClient::putU32(b, 2);
    nbt::DsiClient::putString(b, selected);
    nbt::DsiClient::putString(b, "11:22:33:44:55:66");
    for (int list = 0; list < 3; ++list) {
        nbt::DsiClient::putU32(b, 2);
        nbt::DsiClient::putU32(b, list == 2 ? (connected ? 3 : 1) : 0);
        nbt::DsiClient::putU32(b, list == 2 ? 3 : 0);
    }
    if (!response) nbt::DsiClient::putU32(b, 0);
    return b;
}

static void expect(nbt::PhoneWatch& w, bool k, bool c) {
    bool known, connected; w.snapshot(known, connected);
    assert(known == k && connected == c);
}

int main() {
    char normalized[18];
    assert(nbt::normalizePhoneAddress("aa:bb:cc:dd:ee:ff", normalized));
    assert(!strcmp(normalized, "AA:BB:CC:DD:EE:FF"));
    assert(!nbt::normalizePhoneAddress("", normalized));
    assert(!nbt::normalizePhoneAddress("AA:BB:CC:DD:EE:FFmore", normalized));
    assert(!nbt::normalizePhoneAddress("AA-BB-CC-DD-EE-FF", normalized));
    assert(!nbt::normalizePhoneAddress("AA:BB:CC:DD:EE:GG", normalized));
    fake_dsi::reset();
    nbt::PhoneWatch invalid("not a phone");
    assert(!invalid.start() && !fake_dsi::opened());

    nbt::PhoneWatch w("aa:bb:cc:dd:ee:ff");
    assert(w.start());
    assert(fake_dsi::openedIface == "SGBluetoothGap" && fake_dsi::openedRole == "BSS_GAP");
    expect(w, false, false);
    fake_dsi::attach();
    assert(fake_dsi::calls.size() == 4);
    assert(fake_dsi::calls[1].kind == fake_dsi::Call::kNotify && fake_dsi::calls[1].id == 0x80000001);
    assert(fake_dsi::calls[2].kind == fake_dsi::Call::kNotify && fake_dsi::calls[2].id == 0x80000000);
    assert(fake_dsi::calls[3].kind == fake_dsi::Call::kRequest && fake_dsi::calls[3].id == 0x13);
    std::vector<uint8_t> frame = devices(true);
    fake_dsi::data(0x80000028, &frame[0], (uint32_t)frame.size()); expect(w, true, true);
    frame = devices(false, false);
    fake_dsi::data(0x80000001, &frame[0], (uint32_t)frame.size()); expect(w, true, false);
    frame = devices(true, true, 0, "00:00:00:00:00:01");
    fake_dsi::data(0x80000028, &frame[0], (uint32_t)frame.size()); expect(w, true, false); // other phones ignored
    frame = devices(true, true, 5);
    fake_dsi::data(0x80000028, &frame[0], (uint32_t)frame.size()); expect(w, false, false);
    frame = devices(true);
    fake_dsi::data(0x80000028, &frame[0], (uint32_t)frame.size()); expect(w, true, true);
    fake_dsi::data(0x80000028, &frame[0], 8); expect(w, false, false);
    fake_dsi::data(0x80000028, &frame[0], (uint32_t)frame.size()); expect(w, true, true);
    fake_dsi::detach(); expect(w, false, false);
    fake_dsi::attach(); expect(w, false, false);
    fake_dsi::data(0x80000028, &frame[0], (uint32_t)frame.size()); expect(w, true, true);
    frame.clear();
    nbt::DsiClient::putString(frame, "AA:BB:CC:DD:EE:FF"); nbt::DsiClient::putU32(frame, 0);
    fake_dsi::data(0x80000000, &frame[0], (uint32_t)frame.size()); expect(w, true, false);
    for (size_t i = 0; i < fake_dsi::calls.size(); ++i)
        if (fake_dsi::calls[i].kind == fake_dsi::Call::kRequest) assert(fake_dsi::calls[i].id == 0x13);
    puts("read-only phone watcher against fake DSI: OK");
}
