#!/bin/sh
# Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD (https://github.com/Sq00ky/Supra-iDrive6-Android-Auto)
# Temporary test only. Persistent startup and artwork are separate steps.
set -u
umask 077
MODE=${1:-follow}
case "$MODE" in follow|always) ;; *) echo "Usage: sh test-ram.sh [follow|always]"; exit 1;; esac
if [ "$#" -gt 1 ]; then echo "Too many arguments"; exit 1; fi
if [ ! -d /opt/hmi ]; then echo "Enter the OMAP shell first: on -f /net/hu-omap/ /bin/sh"; exit 1; fi
K=$(dirname "$0")
if [ ! -f "$K/aa-tile" ] || [ ! -f "$K/aa-tile.size" ]; then echo "Incomplete test package"; exit 1; fi
read WANT < "$K/aa-tile.size"
case "$WANT" in ''|*[!0-9]*|0) echo "Invalid binary size metadata"; exit 1;; esac
ACTUAL=$(wc -c < "$K/aa-tile")
if [ "$ACTUAL" -ne "$WANT" ]; then echo "Binary size mismatch; do not run this copy"; exit 1; fi
STATE= PID= EXTRA=
if [ ! -r /dev/shmem/nbt-aad-state ]; then echo "Start stable Android Auto first (state file is missing)"; exit 1; fi
read STATE PID EXTRA < /dev/shmem/nbt-aad-state || :
case "$PID" in ''|*[!0-9]*|0) echo "Invalid Android Auto daemon PID"; exit 1;; esac
if ! kill -0 "$PID" 2>/dev/null; then echo "Android Auto state is stale; start the stable app first"; exit 1; fi
if [ "$MODE" = follow ] && [ "$STATE" != connected ]; then echo "Connect Android Auto before testing follow mode"; exit 1; fi
T=/dev/shmem/aa-tile-test.$$
if ! mkdir "$T"; then echo "Cannot create private RAM test directory"; exit 1; fi
P=$T/aa-tile
L=$T/test.log
CHILD=
finish() {
  trap '' INT TERM
  if [ -n "$CHILD" ]; then kill -TERM "$CHILD" 2>/dev/null || :; wait "$CHILD" 2>/dev/null || :; CHILD=; fi
  N=1
  while [ -f "$K/test$N.log" ]; do N=$((N+1)); done
  if [ -f "$L" ]; then
    if cat "$L" > "$K/test$N.log"; then echo "Log saved: $K/test$N.log"; else echo "USB log copy failed; RAM log retained: $L"; return; fi
  fi
  rm -f "$P" "$L"
  rmdir "$T" 2>/dev/null || :
}
trap 'finish; exit 130' INT
trap 'finish; exit 143' TERM
# USB may be noexec; copying an existing executable supplies execute permission.
if ! cp /bin/ls "$P" || ! cat "$K/aa-tile" > "$P"; then finish; exit 1; fi
ACTUAL=$(wc -c < "$P")
if [ "$ACTUAL" -ne "$WANT" ]; then echo "RAM copy size mismatch"; finish; exit 1; fi
echo "120-second RAM test ($MODE). Stable Android Auto remains installed."
echo "Look for the stock CarLife / n. t. a. (ASIA) tile in Main menu and Media."
echo "Select it to return to Android Auto; check BACK, volume and reverse camera."
echo "In follow mode: disconnect/reconnect the AA phone and check tile visibility."
echo "The helper attempts to hide/unregister the tile when the timer ends."
LD_PRELOAD= LD_LIBRARY_PATH= "$P" "$MODE" 120 > "$L" 2>&1 &
CHILD=$!
wait "$CHILD"
RC=$?
CHILD=
cat "$L"
echo "Helper exit: $RC"
case "$RC" in
  0) echo "Protocol checks passed; confirm visual behavior yourself.";;
  1) echo "Startup, argument or library failure.";;
  2) echo "HMI did not subscribe; no usable tile was confirmed.";;
  4) echo "MOST attachment/client registration failed.";;
  5) echo "Send/cleanup failure; tile removal is not confirmed. Keep the log; reboot if needed.";;
  6) echo "Another helper holds the RAM lock, or the RAM lock is unavailable.";;
  9) echo "Helper crashed. Keep the log and stop testing.";;
  *) echo "Unexpected exit. Keep the log and stop testing.";;
esac
finish
exit "$RC"
