// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
#include "background_connect.hpp"
#include "connection_options.hpp"
#include <assert.h>
#include <stdio.h>

static bool screen(const nbt::BackgroundConnect& p, bool connected = true,
                   bool userExit = false, bool reverse = false, bool park = false,
                   bool camera = false, bool peek = false) {
    return p.visible(connected, userExit, reverse, park, camera, peek);
}

int main() {
    // Both connection sources must obey precisely the same presentation setting.
    for (int autoConnect = 0; autoConnect != 2; ++autoConnect) {
        for (int autoOpen = 0; autoOpen != 2; ++autoOpen) {
            nbt::BackgroundConnect p;
            assert(!screen(p, false));
            if (!autoConnect) assert(nbt::connectionAction(false, false) == nbt::CONNECT);
            assert(nbt::connectionAction(true, false) == nbt::WAIT_FOR_CONNECTION);
            p.sessionStarted(autoOpen != 0);
            assert(screen(p) == (autoOpen != 0));
            assert(p.requestShow(false) == (autoOpen != 0));
            assert(nbt::connectionAction(true, true) == nbt::OPEN);
            assert(p.requestShow(true)); // tile OR explicit menu Open
            assert(screen(p));
            assert(!screen(p, true, true)); // return to iDrive stays respected
            p.dismissed();
            assert(!p.requestShow(false)); // auto-open is once per connection, not a focus loop
            assert(!screen(p));
            assert(p.requestShow(true));
            assert(!screen(p, true, false, true));
            assert(!screen(p, true, false, false, true));
            assert(!screen(p, true, false, false, false, true));
            assert(!screen(p, true, false, false, false, false, true));
            assert(screen(p)); // camera/PDC return after opening
            p.sessionEnded();
            assert(!screen(p, false));
            p.sessionStarted(autoOpen != 0);
            assert(screen(p) == (autoOpen != 0)); // same preference on reconnect
            printf("PASS: connection %s, screen %s\n", autoConnect ? "auto" : "manual", autoOpen ? "auto" : "manual");
        }
    }
    nbt::BackgroundConnect p;
    p.sessionStarted(false);
    // No call to sessionStarted on a setting edit: existing session is unaffected.
    bool changedPreference = true;
    assert(!screen(p));
    assert(!p.requestShow(false)); // stale automatic restoration is not explicit Open
    assert(!screen(p, true, false, true));
    assert(!screen(p)); // leaving a camera does not open unselected AA
    p.sessionEnded(); p.sessionStarted(changedPreference);
    assert(screen(p)); // edited preference takes effect only at the next connection
    changedPreference = false;
    assert(screen(p)); // switching auto-open off does not hide an active session
    p.sessionEnded(); p.sessionStarted(changedPreference);
    assert(!screen(p));
    p.sessionEnded();
    assert(p.requestShow(true)); // explicit selection while connection is finishing
    assert(!screen(p, false));
    p.sessionStarted(false); assert(screen(p));
    puts("PASS: reconnect, deferred settings, explicit Open, idle and camera/PDC gates");
    return 0;
}
