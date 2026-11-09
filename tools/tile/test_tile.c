/* Production protocol handlers against fake DSI streams; no vehicle access. */
#include <assert.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <stdio.h>
#include <unistd.h>
#include <string.h>
static char test_state_path[128];
static char test_lock_path[128];
static int shows;
static ssize_t fake_sendto(int fd, const void* data, size_t length, int flags,
                          const struct sockaddr* address, socklen_t address_length);
#define AA_TILE_STATE_FILE test_state_path
#define AA_TILE_LOCK_FILE test_lock_path
#define sendto fake_sendto
#define main tile_program_main
#include "../../milestone-7/tools/aa_tile.c"
#undef main
#undef sendto

static unsigned request_ids[32], requests, packet_length;
static unsigned char packet[256];
static int send_result;
static union { u64 alignment; char data[512]; } client_storage;

static ssize_t fake_sendto(int fd, const void* data, size_t length, int flags,
                          const struct sockaddr* address, socklen_t address_length) {
    const struct sockaddr_in* sa = (const struct sockaddr_in*)address;
    (void)fd; (void)flags;
    assert(length == 4 && !memcmp(data, "show", 4));
    assert(address_length == sizeof(*sa));
    assert(sa->sin_family == AF_INET && ntohs(sa->sin_port) == 52790);
    assert(ntohl(sa->sin_addr.s_addr) == 0x7f000001UL);
    shows++;
    return 4;
}
static void fake_ctor(void* a, void* b, void* c, int fd, unsigned kind,
                      unsigned command, unsigned id, const void* p, const void* q, int r) {
    (void)a; (void)b; (void)c; (void)fd; (void)p; (void)q; (void)r;
    assert(kind == 0x100 && command == 7);
    assert(requests < 32); request_ids[requests++] = id;
}
static void fake_write(void* stream, const void* data, unsigned length) {
    (void)stream; assert(length <= sizeof(packet));
    memcpy(packet, data, length); packet_length = length;
}
static int fake_send(void* stream, int timeout) { (void)stream; assert(timeout == -1); return send_result; }
static void fake_dtor(void* stream) { (void)stream; }
static void reset(void) {
    g_attached = g_regDone = g_devDone = 1;
    g_done = g_stop = g_errors = g_presses = g_subscribed = 0;
    g_always = 0; g_shown = -1; g_client = 7; g_dev = 0x1234; g_ctrl = 0x2022;
    g_cli = client_storage.data;
    streamCtor = fake_ctor; streamWrite = fake_write;
    streamSend = fake_send; streamDtor = fake_dtor;
    requests = shows = send_result = 0;
}
static void state(const char* word, long pid) {
    FILE* file = fopen(test_state_path, "w"); assert(file);
    fprintf(file, "%s %ld 0\n", word, pid); assert(!fclose(file));
}
static void message(u8* p, u16 fkt, const u8* data, unsigned n) {
    memset(p, 0, 128);
    p[12] = g_dev; p[13] = g_dev >> 8; p[14] = 0x22; p[15] = 0x20;
    p[16] = TILE_FB; p[17] = TILE_INST; p[18] = fkt; p[19] = fkt >> 8;
    p[20] = OP_SET; p[28] = n;
    if (data) memcpy(p + 32, data, n);
}
static void test_state(void) {
    reset(); unlink(test_state_path); assert(!wanted());
    state("connected", getpid()); assert(wanted());
    state("connecting", getpid()); assert(!wanted());
    state("connectedness", getpid()); assert(!wanted());
    state("connected", 0); assert(!wanted());
    state("connected", 2147483647); assert(!wanted());
    g_always = 1; assert(wanted()); g_stop = 1; assert(!wanted());
}
static void test_protocol(void) {
    u8 p[128], subscribe[] = {1, 0x20, 0x22, 0x0c, 0xf1}, press[] = {0};
    reset(); state("connected", getpid());
    message(p, FKT_NOTIF, subscribe, 5); onMessage(p, 37);
    assert(g_subscribed == 1 && requests == 1 && request_ids[0] == REQ_PROCESS_MESSAGE);
    assert(packet_length == 37 && packet[24] == OP_STATUS && packet[36] == 0);
    publish(0); assert(requests == 1); /* no repeated unchanged state */
    state("idle", getpid()); publish(0); assert(requests == 2 && packet[36] == 1);
    message(p, FKT_PRESS, press, 1); onMessage(p, 33); assert(!shows);
    state("connected", getpid()); onMessage(p, 33); assert(shows == 1 && g_presses == 1);
    p[14] = 0x55; onMessage(p, 33); assert(shows == 1);
    p[14] = 0x22; g_stop = 1; onMessage(p, 33); assert(shows == 1);
    g_stop = 0; p[16] = 0x25; onMessage(p, 33); assert(shows == 1);
    message(p, FKT_PRESS, press, 1); onMessage(p, 31); assert(shows == 1);
    p[28] = 100; onMessage(p, 33); assert(shows == 1);
    g_attached = 0; onMessage(p, 128); assert(shows == 1);
}
static void test_cleanup(void) {
    reset(); g_stop = 1; poll();
    assert(g_done && requests == 2 && request_ids[0] == REQ_PROCESS_MESSAGE);
    assert(request_ids[1] == REQ_UNREGISTER_DEVICES);
    assert(packet_length == 12 && r32(packet) == 7 && r32(packet + 4) == 1);
    assert(r16(packet + 8) == TILE_KEY);
    reset(); send_result = -1; g_stop = 1; poll(); assert(!g_done && g_errors == 1);
    reset(); g_devDone = 0; send_result = -1; poll();
    assert(!g_devDone && g_stop && g_errors == 1);
    poll(); assert(g_done && requests == 1); /* never register a device after stop */
    reset(); state("connected", getpid()); send_result = -1;
    publish(0); assert(g_shown == -1 && g_errors == 1);
    reset(); onDetached(0); assert(!g_attached && g_stop && g_errors == 1);
    onAttached(0); assert(!g_attached && !requests);
}
static void test_args_and_lock(void) {
    int secs, fd, result; pid_t child;
    char* ok[] = {"aa-tile", "follow", "120"};
    char* bad[] = {"aa-tile", "follow", "-1"};
    assert(parseArgs(1, ok, &secs) && secs == 120 && !g_always);
    assert(parseArgs(3, ok, &secs) && secs == 120);
    assert(!parseArgs(3, bad, &secs));
    bad[2] = "999999999999999999999999999999999"; assert(!parseArgs(3, bad, &secs));
    bad[2] = "120x"; assert(!parseArgs(3, bad, &secs));
    bad[1] = "other"; assert(!parseArgs(3, bad, &secs));
    fd = lockInstance(); assert(fd >= 0);
    child = fork(); assert(child >= 0);
    if (!child) { int other = lockInstance(); _exit(other >= 0 ? 1 : 0); }
    assert(waitpid(child, &result, 0) == child && WIFEXITED(result) && !WEXITSTATUS(result));
    close(fd);
    fd = lockInstance(); assert(fd >= 0); close(fd);
}
int main(void) {
    snprintf(test_state_path, sizeof(test_state_path), "/tmp/aa-tile-state-%ld", (long)getpid());
    snprintf(test_lock_path, sizeof(test_lock_path), "/tmp/aa-tile-lock-%ld", (long)getpid());
    test_state(); test_protocol(); test_cleanup(); test_args_and_lock();
    unlink(test_state_path); unlink(test_lock_path);
    puts("PASS: live-state gates, MOST packets/presses, failed sends/cleanup, args and instance lock");
    return 0;
}
