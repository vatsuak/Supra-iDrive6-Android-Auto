/*
 * nbt-aa-tile - Android Auto tile in the NBT EVO main menu, as a program separate from nbt-aad.
 *
 * Mechanism found by RRudkinp (Sq00ky/Supra-iDrive6-Android-Auto issue #55, his nbt-aad tile build):
 * the program acts as the MOST "CarLife" device (key 0x2471 = FBlock 0x24, instance 0x71):
 *   - registers the device with request 0x0 (registerDevices: client, 1, 0x2471);
 *   - when the iDrive subscribes (Set fkt 0x001: 01 <address> <fkt>) it answers 0xCF1 (AppState) with a Status
 *     (op 0xC, 1 byte: 0 = tile shown, 1 = hidden) and every other function with an Error (op 0xF, 20 10 <fkt>);
 *   - when the driver presses the tile or the Media/Radio entry (Set fkt 0xCE8, 1 byte) it sends "show" to
 *     nbt-aad's control port (UDP 127.0.0.1:52790), the same message the iDrive Android Auto menu entry sends;
 *   - on exit it hides the tile and unregisters the device (request 0x4).
 * As in that patch, messages are only sent from the DSI callback thread.
 *
 * It never sends setCommunicationCtrl (0xC) or any other request that changes the MOST setup.
 *
 * Usage:  aa-tile [always|follow] [seconds]
 *   always  = tile always shown (testing)
 *   follow  = tile shown only while Android Auto is connected (/dev/shmem/nbt-aad-state = "connected")
 *   seconds = exit by itself after N seconds (0 = until Ctrl+C / kill)
 *
 * The DSI/MOST client is derived from nbt-aad (dsi_client.cpp, most/msg.hpp, most/ids.hpp):
 *   Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD (https://github.com/Sq00ky/Supra-iDrive6-Android-Auto)
 *   PolyForm Noncommercial 1.0.0. Noncommercial use only.
 * Upstream standalone implementation by deathwalker80; adapted here for the QNX SDP 6.5 SDK.
 * Local changes and pinned upstream revision: aa_tile.UPSTREAM.txt.
 */
typedef unsigned int u32; typedef unsigned short u16; typedef unsigned char u8;
typedef unsigned long long u64;

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <dlfcn.h>
#include <signal.h>
#include <pthread.h>
#include <errno.h>
#include <limits.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

#define AA_TILE_VERSION "5-supra-ram1"
#ifndef AA_TILE_STATE_FILE
#define AA_TILE_STATE_FILE "/dev/shmem/nbt-aad-state"
#endif
#ifndef AA_TILE_LOCK_FILE
#define AA_TILE_LOCK_FILE "/dev/shmem/aa-tile.lock"
#endif

#define TILE_KEY   0x2471
#define TILE_FB    0x24
#define TILE_INST  0x71
#define FKT_NOTIF  0x001
#define FKT_STATE  0xCF1   /* AppState: 0 shown, 1 hidden */
#define FKT_PRESS  0xCE8   /* Set from the iDrive: 0 = main-menu tile, other = Media/Radio entry */
#define OP_SET     0x0
#define OP_STATUS  0xC
#define OP_ERROR   0xF

#define REQ_REGISTER_DEVICES   0x0
#define REQ_PROCESS_MESSAGE    0x2
#define REQ_UNREGISTER_DEVICES 0x4
#define REQ_REGISTER_CLIENT    0xF

typedef void (*FnConnCtor)(void*);
typedef int  (*FnConnAdd)(void*, void*);
typedef void (*FnConnStart)(void*);
typedef void (*FnCliCtor)(void*, const char*, const char*, int, int);
typedef void (*FnSetNotif)(void*, unsigned);
typedef void (*FnStreamCtor)(void*, void*, void*, int, unsigned, unsigned, unsigned, const void*, const void*, int);
typedef void (*FnStreamWrite)(void*, const void*, unsigned);
typedef int  (*FnStreamSend)(void*, int);
typedef void (*FnStreamDtor)(void*);

static FnConnCtor connCtor; static FnConnAdd connAdd; static FnConnStart connStart; static FnCliCtor cliCtor;
static FnSetNotif setNotif; static FnStreamCtor streamCtor; static FnStreamWrite streamWrite;
static FnStreamSend streamSend; static FnStreamDtor streamDtor; static void* vtable;

static void* g_conn; static char* g_cli;
static volatile int g_attached, g_regDone, g_devDone, g_done, g_errors;
static volatile sig_atomic_t g_stop;
static volatile int g_callbacks, g_presses, g_subscribed;
static u32 g_client = 0xffffffffu; static u16 g_dev;
static u16 g_ctrl;                       /* MOST address of the iDrive, learned from its first subscription */
static int g_always;                     /* 1 = always shown */
static int g_shown = -1;                 /* last AppState sent: -1 none, 0 hidden, 1 shown */

static void* need(void* lib, const char* name) {
    void* p = dlsym(lib, name);
    printf("[dsi] dlsym %-60.60s %s\n", name, p ? "ok" : "MISSING");
    return p;
}

/* DSI stream encoding: scalars aligned to their size from the start of the payload */
typedef struct { u8 b[256]; unsigned n; } Buf;
static void pad(Buf* v, unsigned a) { while (v->n % a) v->b[v->n++] = 0; }
static void p32(Buf* v, u32 x) { pad(v, 4); v->b[v->n++] = x; v->b[v->n++] = x >> 8; v->b[v->n++] = x >> 16; v->b[v->n++] = x >> 24; }
static void p16(Buf* v, u16 x) { pad(v, 2); v->b[v->n++] = x; v->b[v->n++] = x >> 8; }
static void p8(Buf* v, u8 x) { v->b[v->n++] = x; }
static void pstr(Buf* v, const char* s) { u32 n = strlen(s) + 1; p32(v, n); memcpy(v->b + v->n, s, n); v->n += n; pad(v, 4); }
static u32 r32(const u8* p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((u32)p[3] << 24); }
static u16 r16(const u8* p) { return p[0] | (p[1] << 8); }

static void hex(const char* tag, const u8* p, u32 n) {
    u32 i; printf("%s len=%u:", tag, n);
    for (i = 0; i < n && i < 64; ++i) printf(" %02x", p[i]);
    printf("\n"); fflush(0);
}

static int sendRequest(u32 id, const Buf* v) {
    u64 st[(0xBC + 64) / 8 + 1];
    char* s = (char*)st;
    int fd, rc;
    if (!g_attached) return -1;
    memset(st, 0, sizeof(st));
    fd = *(int*)(g_cli + 0x140);
    streamCtor(s, g_cli + 0x130, g_cli + 0x138, fd, 0x100u, 7u, id, g_cli + 0x110, g_cli + 0x118, 0);
    if (v && v->n) streamWrite(s, v->b, v->n);
    rc = streamSend(s, -1);
    streamDtor(s);
    printf("[tx] request 0x%x -> rc=%d\n", id, rc); fflush(0);
    return rc;
}

/* registerDevices / unregisterDevices: u32 client, u32 count, u16 keys */
static int sendDevice(u32 req) {
    Buf v; v.n = 0;
    p32(&v, g_client); p32(&v, 1); p16(&v, TILE_KEY); pad(&v, 4);
    hex("[tx] device", v.b, v.n);
    return sendRequest(req, &v);
}

/* processMessage(client, MessageType) from device 0x2471 to the iDrive */
static int sendMsg(u16 fkt, u8 op, const u8* data, u32 n) {
    Buf v; u32 i; v.n = 0;
    p32(&v, g_client);
    p32(&v, 0); p32(&v, 1); p32(&v, 0);                 /* txType 0, TXControl variant, 0 */
    p16(&v, g_ctrl); p16(&v, g_dev); p8(&v, TILE_FB); p8(&v, TILE_INST); p16(&v, fkt); p8(&v, op);
    p32(&v, g_client);                                   /* tag */
    p32(&v, n);
    for (i = 0; i < n; ++i) p8(&v, data[i]);
    printf("[tx] FB 24.71 fkt 0x%03x op 0x%X -> 0x%04x\n", fkt, op, g_ctrl);
    hex("[tx] msg", v.b, v.n);
    return sendRequest(REQ_PROCESS_MESSAGE, &v);
}

/* Wanted AppState: always, or from nbt-aad's state file ("connected <pid> <overlay>") */
static int wanted(void) {
    char b[80], state[24]; long pid; int fd, n;
    if (g_stop) return 0;
    if (g_always) return 1;
    fd = open(AA_TILE_STATE_FILE, O_RDONLY);
    if (fd < 0) return 0;
    n = read(fd, b, sizeof(b) - 1);
    close(fd);
    if (n <= 0) return 0;
    b[n] = 0;
    if (sscanf(b, "%23s %ld", state, &pid) != 2 || strcmp(state, "connected") || pid <= 0 || pid > INT_MAX)
        return 0;
    return kill((pid_t)pid, 0) == 0 || errno == EPERM;
}

static void publish(int force) {
    int w; u8 d;
    if (!g_ctrl || !g_devDone) return;
    w = wanted();
    if (!force && w == g_shown) return;
    d = w ? 0 : 1;
    if (sendMsg(FKT_STATE, OP_STATUS, &d, 1) < 0) { ++g_errors; return; }
    g_shown = w;
    printf("[tile] %s\n", w ? "SHOWN" : "hidden"); fflush(0);
}

/* "show" to nbt-aad's control port, like the iDrive Android Auto menu entry */
static void sendShow(void) {
    struct sockaddr_in sa; int s, rc;
    memset(&sa, 0, sizeof(sa));
    sa.sin_family = AF_INET;
#ifdef __QNXNTO__
    sa.sin_len = sizeof(sa);
#endif
    sa.sin_port = htons(52790);
    sa.sin_addr.s_addr = htonl(0x7f000001UL);
    s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s < 0) { printf("[show] socket failed\n"); fflush(0); return; }
    rc = sendto(s, "show", 4, 0, (const struct sockaddr*)&sa, sizeof(sa));
    close(s);
    printf("[show] 'show' to nbt-aad (127.0.0.1:52790) -> %d\n", rc); fflush(0);
}

/* periodic work, always from the callback thread */
static void poll(void) {
    if (g_done || !g_regDone) return;
    if (!g_devDone) {
        if (g_stop) { g_done = 1; return; }
        if (sendDevice(REQ_REGISTER_DEVICES) < 0) { ++g_errors; g_stop = 1; return; }
        g_devDone = 1;
        printf("[tile] registered device 0x%04X (client %u, device 0x%04X), mode %s\n",
               TILE_KEY, g_client, g_dev, g_always ? "always" : "follow"); fflush(0);
        return;
    }
    if (g_stop) {
        if (g_ctrl) { u8 d = 1; if (sendMsg(FKT_STATE, OP_STATUS, &d, 1) < 0) { ++g_errors; return; } }
        if (sendDevice(REQ_UNREGISTER_DEVICES) < 0) { ++g_errors; return; }
        g_done = 1;
        printf("[tile] tile hidden and device unregistered\n"); fflush(0);
        return;
    }
    publish(0);
}

static void onAttached(void* self) {
    static const u32 attrs[] = { 0xC0000002u, 0xC0000003u, 0xC0000001u, 0x80000001u, 0x80000002u,
                                 0x80000003u, 0x80000004u, 0x80000005u, 0x80000006u, 0x80000007u };
    Buf v; unsigned i;
    (void)self;
    if (g_stop) return;
    g_attached = 1;
    printf("[dsi] attached: registering MOST client 'AA_TILE'\n"); fflush(0);
    v.n = 0; pstr(&v, "AA_TILE");
    sendRequest(REQ_REGISTER_CLIENT, &v);
    for (i = 0; i < sizeof(attrs) / sizeof(attrs[0]); ++i) setNotif(g_cli, attrs[i]);
}

static void onDetached(void* self) {
    (void)self; g_attached = 0; g_stop = 1; ++g_errors;
    printf("[dsi] detached; stopping this test\n"); fflush(0);
}

static void onMessage(const u8* pl, u32 len) {
    u16 dst, fkt; u8 fb, inst, op; u32 n; const u8* d;
    if (!g_attached || !g_regDone || !g_devDone || !pl || len < 32) return;      /* pointer and length always checked */
    dst = r16(pl + 12); fb = pl[16]; inst = pl[17]; fkt = r16(pl + 18); op = pl[20];
    n = r32(pl + 28); d = pl + 32;
    if (n > len - 32) return;          /* never read past the buffer */
    if (n > 64) n = 64;                /* defensive cap on the data we log/use */
    if (fb != TILE_FB || inst != TILE_INST || dst != g_dev || op != OP_SET) return;
    printf("[rx] FB 24.71 fkt 0x%03x Set from 0x%04x\n", fkt, r16(pl + 14));
    hex("[rx] data", d, n);
    if (fkt == FKT_NOTIF && n == 5 && d[0] == 1) {
        u16 f = (d[3] << 8) | d[4];
        g_ctrl = (d[1] << 8) | d[2];
        g_subscribed++;
        printf("[rx] iDrive (0x%04x) subscribed to function 0x%03x\n", g_ctrl, f); fflush(0);
        if (f == FKT_STATE) publish(1);
        else { u8 e[4]; e[0] = 0x20; e[1] = 0x10; e[2] = d[3]; e[3] = d[4]; sendMsg(FKT_NOTIF, OP_ERROR, e, 4); }
        return;
    }
    if (fkt == FKT_PRESS && n == 1 && g_ctrl && r16(pl + 14) == g_ctrl && wanted()) {
        g_presses++;
        printf("[tile] pressed: %s\n", d[0] == 0 ? "main-menu tile" : "Media/Radio entry");
        fflush(0);
        sendShow();
        return;
    }
}

static void onData(void* self, void* is) {
    const char* s = (const char*)is;
    u32 id, len; const u8* pl;
    (void)self;
    g_callbacks++;
    if (!g_attached) return;          /* nothing is processed while detached */
    if (s) {
        id = *(const u32*)(s + 0x48);
        pl = *(const u8* const*)(s + 0x10); len = *(const u32*)(s + 0x08);
        if (pl) {
            if (id == 0x80000000u && len >= 6) {
                g_client = r32(pl); g_dev = r16(pl + 4);
                printf("[rx] registered: client=%u device=0x%04X%s\n", g_client, g_dev,
                       g_client == 0xffffffffu ? " (REFUSED)" : "");
                fflush(0);
                if (g_client != 0xffffffffu) { setNotif(g_cli, 0xC0000000u); g_regDone = 1; }
                else g_errors++;
            } else if (id == 0x80000001u) {
                onMessage(pl, len);
            }
        }
    }
    poll();
}

static void* thr(void* a) { (void)a; connStart(g_conn); printf("[dsi] start() returned\n"); fflush(0); return 0; }

static void onSignal(int sig) { (void)sig; g_stop = 1; }

/* RAM-test build: fatal signals report to the RAM log, never to persistent storage. */
static void onFatal(int sig) {
    const char message[] = "aa-tile fatal signal; test stopped\n";
    (void)sig;
    write(STDERR_FILENO, message, sizeof(message) - 1);
    _exit(9);
}

static int lockInstance(void) {
    struct flock lock;
    int fd = open(AA_TILE_LOCK_FILE, O_RDWR | O_CREAT, 0600);
    if (fd < 0) return -1;
    memset(&lock, 0, sizeof(lock));
    lock.l_type = F_WRLCK; lock.l_whence = SEEK_SET;
    if (fcntl(fd, F_SETLK, &lock) < 0) { close(fd); return -1; }
    return fd; /* Keep open until process exit; the kernel releases the lock. */
}

static int parseArgs(int argc, char** argv, int* secs) {
    char* end; unsigned long duration;
    if (argc > 3) return 0;
    if (argc > 1 && strcmp(argv[1], "follow") && strcmp(argv[1], "always")) return 0;
    *secs = 120;
    if (argc > 2) {
        if (!argv[2][0] || argv[2][0] == '-') return 0;
        errno = 0; duration = strtoul(argv[2], &end, 10);
        if (errno || *end || duration > 86400) return 0;
        *secs = (int)duration;
    }
    g_always = argc > 1 && !strcmp(argv[1], "always");
    return 1;
}

int main(int argc, char** argv) {
    void* lib = 0; void** vt; pthread_t t; int i, secs, ticks, instanceFd;
    static const char* names[] = { "/opt/sys/lib/libsys_dsi_colibry.cpp-ne.so.8",
        "/fs/sda0/opt/sys/lib/libsys_dsi_colibry.cpp-ne.so.8", "libsys_dsi_colibry.cpp-ne.so.8", 0 };
    if (!parseArgs(argc, argv, &secs)) {
        fprintf(stderr, "Usage: aa-tile [follow|always] [seconds: 0..86400, default 120]\n"); return 1;
    }
    instanceFd = lockInstance();
    if (instanceFd < 0) { fprintf(stderr, "aa-tile already running or RAM lock unavailable\n"); return 6; }
    printf("nbt-aa-tile " AA_TILE_VERSION " (mode %s, %s) - works with any nbt-aad that has the control port and state file\n",
           g_always ? "always" : "follow", secs ? "timed" : "until Ctrl+C"); fflush(0);
    signal(SIGINT, onSignal); signal(SIGTERM, onSignal);
    signal(SIGILL, onFatal); signal(SIGABRT, onFatal); signal(SIGFPE, onFatal);
    signal(SIGBUS, onFatal); signal(SIGSEGV, onFatal);
#ifdef SIGEMT
    signal(SIGEMT, onFatal);
#endif
    for (i = 0; names[i] && !lib; ++i) { lib = dlopen(names[i], RTLD_NOW | RTLD_GLOBAL); printf("[dsi] dlopen %s -> %s\n", names[i], lib ? "OK" : dlerror()); }
    if (!lib) return 1;
    connCtor = (FnConnCtor)need(lib, "_ZN14CDSIConnectionC1Ev");
    connAdd = (FnConnAdd)need(lib, "_ZN14CDSIConnection3addER10CDSIClient");
    connStart = (FnConnStart)need(lib, "_ZN14CDSIConnection5startEv");
    cliCtor = (FnCliCtor)need(lib, "_ZN10CDSIClientC1EPKcS1_ii");
    setNotif = (FnSetNotif)need(lib, "_ZN10CDSIClient15setNotificationEj");
    streamCtor = (FnStreamCtor)need(lib, "_ZN11CDSIOStreamC1ER11CDSIChannelP13CDSITCPSocketiN3DSI11RequestTypeENS4_7CommandEjRK8SPartyIDS9_i");
    streamWrite = (FnStreamWrite)need(lib, "_ZN11CDSIOStream5writeEPKvj");
    streamSend = (FnStreamSend)need(lib, "_ZN11CDSIOStream4sendEi");
    streamDtor = (FnStreamDtor)need(lib, "_ZN11CDSIOStreamD1Ev");
    vtable = need(lib, "_ZTV10CDSIClient");
    if (!connCtor || !connAdd || !connStart || !cliCtor || !setNotif || !streamCtor || !streamWrite || !streamSend || !streamDtor || !vtable) return 1;
    g_conn = calloc(1, 0x8c + 64); g_cli = (char*)calloc(1, 0x14c + 64);
    if (!g_conn || !g_cli) return 1;
    connCtor(g_conn);
    cliCtor(g_cli, "DSYSMOSTServer", "MOSTSubSystem", 4, 5);
    vt = (void**)calloc(32, sizeof(void*));
    if (!vt) return 1;
    memcpy(vt, (char*)vtable + 8, 32 * sizeof(void*));
    vt[3] = (void*)onAttached; vt[4] = (void*)onDetached; vt[7] = (void*)onData;
    *(void***)g_cli = vt;
    printf("[dsi] add -> %d\n", connAdd(g_conn, g_cli)); fflush(0);
    if (pthread_create(&t, 0, thr, 0) != 0) { printf("[dsi] thread FAILED\n"); return 1; }
    for (ticks = 0; !g_stop; ++ticks) {          /* one round every 250 ms */
        usleep(250000);
        if (secs && ticks >= secs * 4) g_stop = 1;
        if (ticks % 40 == 0)
            printf("[state] callbacks=%d subscriptions=%d presses=%d shown=%d iDrive=0x%04x\n",
                   g_callbacks, g_subscribed, g_presses, g_shown, g_ctrl), fflush(0);
    }
    printf("[tile] stopping: waiting for a callback to hide the tile (max 3 s)\n"); fflush(0);
    for (i = 0; i < 30 && !g_done && g_attached; ++i) usleep(100000);
    printf("RESULT: attached=%d registered=%d device=%d subscriptions=%d presses=%d callbacks=%d clean=%d errors=%d\n",
           g_attached, g_regDone, g_devDone, g_subscribed, g_presses, g_callbacks, g_done, g_errors);
    fflush(0);
    if (!g_regDone) exit(4);
    if (!g_done || g_errors) exit(5);
    exit(g_subscribed ? 0 : 2);
    return 0;
}
