// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
#include "../rhmiapp/controls_entry.hpp"
#include "background_connect.hpp"
#include "../rhmiapp/entry_key.hpp"
#include <assert.h>
#include <stdio.h>

int main() {
    typedef nbt::ControlsEntry C;
    C c;
    assert(c.poll(100, true, true, 0) == C::NONE); // accidental BACK: no menu request
    c.begin(100);
    unsigned token = c.token();
    assert(c.pending());
    assert(c.poll(200, true, false, 0) == C::NONE); // stale hidden record is not an ACK
    assert(c.poll(300, true, true, token) == C::NONE); // input still belongs to phone
    assert(c.poll(600, true, true, 0) == C::SEND); // lost UDP: bounded retry
    assert(c.poll(700, true, false, token) == C::OPEN_MENU);
    assert(!c.pending());
    assert(c.poll(800, true, false, token) == C::NONE); // navigate just once
    c.begin(1000);
    assert(c.poll(1100, true, false, token) == C::NONE); // previous visit's ACK
    assert(c.poll(6000, true, true, 0) == C::FAILED);
    assert(!c.pending());
    assert(c.poll(6500, true, false, c.token()) == C::NONE); // no late surprise navigation
    c.begin(7000);
    assert(c.poll(7000, false, false, 0) == C::OPEN_MENU); // stopped / daemon exited
    c.begin(8000);
    c.cancel();
    assert(c.poll(8100, true, false, c.token()) == C::NONE); // newer explicit Open
    c.begin(0xffffff00u);
    assert(c.poll(0x100u, true, true, 0) == C::SEND); // monotonic wrap
    assert(c.poll(0x1300u, true, true, 0) == C::FAILED);
    for (int autoOpen = 0; autoOpen < 2; ++autoOpen) {
        nbt::BackgroundConnect b;
        b.sessionStarted(autoOpen != 0);
        b.requestShow(true);
        assert(b.visible(true, false, false, false, false, false));
        c.begin(10000);
        b.dismissed(); // daemon processes controls without ending session
        assert(!b.requestShow(false)); // phone/warning restore cannot reclaim projection
        assert(!b.visible(true, false, false, false, false, false));
        assert(c.poll(10100, true, false, c.token()) == C::OPEN_MENU);
        assert(b.requestShow(true)); // tile or Open row grants ownership again
        assert(b.visible(true, false, false, false, false, false));
        assert(!b.visible(true, false, true, false, false, false)); // camera priority
    }
    assert(nbt::entrykey::decide(true, true, false, false) == nbt::entrykey::kShow);
    assert(nbt::entrykey::decide(true, true, true, false) == nbt::entrykey::kNothing);
    puts("PASS: controls ACK, stale states, retries, timeout, stopped daemon, cancellation, wrap, explicit reopening");
}
