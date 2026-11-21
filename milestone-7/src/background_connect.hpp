// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD
#ifndef NBT_BACKGROUND_CONNECT_HPP
#define NBT_BACKGROUND_CONNECT_HPP

namespace nbt {
// A background connection does not own the screen until an explicit local
// selection. Phone focus requests and camera/PDC returns cannot grant it.
class BackgroundConnect {
    bool enabled_;
    bool selected_;
public:
    BackgroundConnect() : enabled_(true), selected_(false) {}
    // Snapshot the preference once per connection. Editing settings during a
    // session must not suddenly show/hide AA. Explicit pending Open is retained.
    void sessionStarted(bool automaticallyOpen) { enabled_ = !automaticallyOpen; }
    bool waitingForSelection() const { return enabled_ && !selected_; }
    void selected() { selected_ = true; }
    void dismissed() { enabled_ = true; selected_ = false; }
    bool requestShow(bool explicitSelection) {
        if (explicitSelection) selected();
        return !waitingForSelection();
    }
    void sessionEnded() { enabled_ = true; selected_ = false; }
    bool visible(bool connected, bool userExit, bool reverse,
                 bool park, bool camera, bool driveModePeek) const {
        return connected && !waitingForSelection() &&
               !userExit && !reverse && !park && !camera && !driveModePeek;
    }
};
}
#endif
