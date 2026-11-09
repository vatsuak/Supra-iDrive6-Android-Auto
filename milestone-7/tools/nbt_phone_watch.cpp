// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD (https://github.com/Sq00ky/Supra-iDrive6-Android-Auto)
#include "../src/phone_watch.hpp"
#include <signal.h>
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <time.h>

namespace {
volatile sig_atomic_t stopped = 0;
void stop(int) { stopped = 1; }
uint32_t nowMs() {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)ts.tv_sec * 1000u + (uint32_t)(ts.tv_nsec / 1000000);
}
}

int main(int argc, char** argv) {
    if (argc != 3) { fprintf(stderr, "usage: nbt-phone-watch AA:BB:CC:DD:EE:FF state-file\n"); return 2; }
    char address[18];
    if (!nbt::normalizePhoneAddress(argv[1], address)) return 2;
    signal(SIGTERM, stop); signal(SIGINT, stop); signal(SIGPIPE, SIG_IGN);
    pid_t parent = getppid();
    if (parent <= 1) return 1;
    // Deliberately process-lifetime allocation: DsiClient's thread cannot be
    // joined/unloaded. OS process teardown owns it, never the HMI process.
    nbt::PhoneWatch* watch = new nbt::PhoneWatch(address);
    if (!watch->start()) return 1;
    char temporary[256];
    if (snprintf(temporary, sizeof(temporary), "%s.%ld.tmp", argv[2], (long)getpid()) >= (int)sizeof(temporary)) return 2;
    while (!stopped && getppid() == parent) {
        bool known, connected;
        watch->snapshot(known, connected);
        int fd = open(temporary, O_WRONLY | O_CREAT | O_TRUNC, 0600);
        if (fd < 0) return 1;
        char line[96];
        int n = snprintf(line, sizeof(line), "v1 %u %u %u %u\n", (unsigned)getpid(), nowMs(), known ? 1u : 0u, connected ? 1u : 0u);
        ssize_t written = write(fd, line, (size_t)n);
        close(fd);
        if (written != n || rename(temporary, argv[2]) != 0) { unlink(temporary); return 1; }
        sleep(1);
    }
    unlink(temporary);
    // The parent binds the state file to this PID and checks freshness; leaving
    // the last atomic record cannot make another watcher's telemetry look fresh.
    return 0;
}
