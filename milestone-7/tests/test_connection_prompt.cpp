// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
#include "../rhmiapp/connection_prompt.hpp"
#include "../src/phone_watch_state.hpp"
#include <assert.h>
#include <stdio.h>

using nbt::ConnectionPrompt;
typedef ConnectionPrompt P;

static P::Effect poll(P& p, uint32_t t, bool known = true, bool connected = true,
                      bool blocked = false, bool running = false, bool enabled = true) {
    return p.poll(t, enabled, known, connected, blocked, running);
}

int main() {
    P p;
    assert(poll(p, 0) == P::NONE);
    assert(poll(p, 1999) == P::NONE);
    assert(poll(p, 2000) == P::SHOW);
    assert(poll(p, 3000) == P::NONE);
    p.dismiss();
    assert(poll(p, 4000) == P::NONE); // no duplicate
    assert(poll(p, 5000, false) == P::NONE);
    assert(poll(p, 15000, false) == P::NONE); // watcher loss is not a disconnect
    assert(poll(p, 20000) == P::NONE);
    assert(poll(p, 22000) == P::NONE);
    assert(poll(p, 23000, true, false) == P::NONE);
    assert(poll(p, 27000, true, false) == P::NONE);
    assert(poll(p, 27500) == P::NONE); // brief Bluetooth gap does not rearm
    assert(poll(p, 30000, true, false) == P::NONE);
    assert(poll(p, 35000, true, false) == P::NONE);
    assert(poll(p, 36000) == P::NONE);
    assert(poll(p, 38000) == P::SHOW);
    assert(poll(p, 58000) == P::HIDE); // timeout consumes the connection
    assert(poll(p, 59000) == P::NONE);

    p.reset();
    assert(poll(p, 0, true, true, true) == P::NONE);
    assert(poll(p, 5000, true, true, true) == P::NONE);
    assert(poll(p, 6000) == P::SHOW); // deferred while reverse/call/another popup owns the UI
    assert(poll(p, 6100, true, true, true) == P::HIDE);
    assert(poll(p, 6200) == P::NONE);

    p.reset();
    assert(poll(p, 0, true, true, false, true) == P::NONE);
    assert(poll(p, 5000, true, true, false, true) == P::NONE); // no second start
    assert(poll(p, 6000, true, true, false, false, false) == P::NONE); // setting off
    assert(poll(p, 7000) == P::SHOW);
    assert(poll(p, 7100, false) == P::HIDE); // stale telemetry closes an automatic popup

    p.reset();
    assert(poll(p, 0) == P::NONE);
    assert(poll(p, 1999, false) == P::NONE);
    assert(poll(p, 2000) == P::NONE);
    assert(poll(p, 3999) == P::NONE);
    assert(poll(p, 4000) == P::SHOW); // unknown breaks the connection debounce
    assert(poll(p, 4001, true, true, false, true) == P::HIDE);

    p.reset();
    assert(!p.test(0, true, false));
    assert(!p.test(0, false, true));
    assert(p.test(0, false, false));
    assert(!p.test(1, false, false));
    assert(poll(p, 1000, false, false, false, false, false) == P::NONE);
    assert(poll(p, 20000, false, false, false, false, false) == P::HIDE);

    p.reset();
    assert(poll(p, 0xffffff00u) == P::NONE);
    assert(poll(p, (uint32_t)(0xffffff00u + 2000u)) == P::SHOW); // uptime wrap

    nbt::PhoneWatchState s;
    assert(s.parse("v1 123 1000 1 1\n", 123, 2000) && s.known && s.connected);
    assert(!s.parse("v1 124 1000 1 1\n", 123, 2000) && !s.known);
    assert(!s.parse("v1 123 1000 1 1\n", 123, 4001));
    assert(!s.parse("v1 123 1000 1\n", 123, 2000));
    assert(!s.parse("v1 123 1000 0 1\n", 123, 2000));
    assert(!s.parse("v1 123 1000 2 1\n", 123, 2000));
    assert(!s.parse("v1 123 1000 1 1 extra", 123, 2000));
    assert(!s.parse("v1 123 3000 1 1", 123, 2000));
    assert(s.parse("v1 123 4294967040 1 0", 123, 100) && s.known && !s.connected);
    puts("connection prompt policy and watcher freshness: OK");
}
