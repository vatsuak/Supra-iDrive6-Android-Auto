// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD (https://github.com/Sq00ky/Supra-iDrive6-Android-Auto)
#include "phone_watch.hpp"
#include "bluetooth_manager.hpp"
#include <string.h>

namespace nbt {
namespace {
const uint32_t kGetDevices = 0x13, kDevices = 0x80000028;
const uint32_t kChanged = 0x80000001, kDisconnected = 0x80000000;
}

PhoneWatch::PhoneWatch(const char* address) : valid_(false), known_(false), connected_(false) {
    address_[0] = 0;
    valid_ = normalizePhoneAddress(address, address_);
    pthread_mutex_init(&mutex_, NULL);
}

// Production owns this object until process exit: DsiClient has no close/join API.
// The standalone helper deliberately never unloads a callback-bearing instance.
PhoneWatch::~PhoneWatch() { pthread_mutex_destroy(&mutex_); }

bool PhoneWatch::start() {
    if (!valid_) return false;
    client_.setQuiet(true);
    client_.setCallbacks(&attached, &data, this);
    client_.setDetachCallback(&detached);
    return client_.open(DSI_SERVICE_BLUETOOTH_GAP, DSI_ROLE_BLUETOOTH_GAP, DSI_GAP_MAJOR, DSI_GAP_MINOR);
}

void PhoneWatch::publish(bool known, bool connected) {
    pthread_mutex_lock(&mutex_);
    known_ = known;
    connected_ = known && connected;
    pthread_mutex_unlock(&mutex_);
}

void PhoneWatch::snapshot(bool& known, bool& connected) {
    pthread_mutex_lock(&mutex_);
    known = known_; connected = connected_;
    pthread_mutex_unlock(&mutex_);
}

void PhoneWatch::attached(DsiClient* c, void* user) {
    static_cast<PhoneWatch*>(user)->publish(false, false);
    c->setNotification(kChanged);
    c->setNotification(kDisconnected);
    c->sendRequest(kGetDevices, std::vector<uint8_t>());
}

void PhoneWatch::detached(DsiClient*, void* user) {
    static_cast<PhoneWatch*>(user)->publish(false, false);
}

void PhoneWatch::data(DsiClient* c, uint32_t, uint32_t id, uint32_t,
                      const uint8_t* payload, uint32_t len, void* user) {
    PhoneWatch* w = static_cast<PhoneWatch*>(user);
    if (id == kDisconnected) {
        GapReader r(payload, len);
        std::string address = r.str();
        r.u32(); // reason
        char normalized[18];
        if (r.ok() && normalizePhoneAddress(address.c_str(), normalized) && !strcmp(normalized, w->address_))
            w->publish(true, false);
        c->sendRequest(kGetDevices, std::vector<uint8_t>());
        return;
    }
    if (id != kDevices && id != kChanged) return;
    // Validate parallel lists instead of treating a malformed/error response as
    // an empty list (which would incorrectly rearm a dismissed notification).
    GapReader r(payload, len);
    uint32_t error = id == kDevices ? r.u32() : 0;
    std::vector<std::string> names = r.strList(), addresses = r.strList();
    std::vector<uint32_t> cod = r.u32List(), security = r.u32List(), connection = r.u32List();
    if (id == kChanged) r.u32(); // reason
    if (!r.ok() || error || addresses.size() != names.size() || addresses.size() != cod.size() ||
        addresses.size() != security.size() || addresses.size() != connection.size()) {
        w->publish(false, false);
        return;
    }
    bool connected = false;
    for (size_t i = 0; i < addresses.size(); ++i) {
        char normalized[18];
        if (!normalizePhoneAddress(addresses[i].c_str(), normalized) || connection[i] > 3) {
            w->publish(false, false);
            return;
        }
        if (!strcmp(normalized, w->address_) && connection[i] >= 2) connected = true;
    }
    w->publish(true, connected);
}
} // namespace nbt
