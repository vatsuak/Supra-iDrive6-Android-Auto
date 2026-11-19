// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD
#ifndef NBT_CONNECTION_OPTIONS_HPP
#define NBT_CONNECTION_OPTIONS_HPP
namespace nbt {
// Persistent flags intentionally independent of the native-tile visibility flag.
static const char kAutoConnectFlag[] = "autostart"; // preserve the existing preference
static const char kAutoOpenFlag[] = "auto-open";    // absent = explicit opening only

enum ConnectionAction { CONNECT, WAIT_FOR_CONNECTION, OPEN };
inline ConnectionAction connectionAction(bool running, bool connected) {
    return connected ? OPEN : running ? WAIT_FOR_CONNECTION : CONNECT;
}
}
#endif
