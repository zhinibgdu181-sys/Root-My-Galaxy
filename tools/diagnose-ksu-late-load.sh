#!/system/bin/sh

# Samsung SM-S9360 / pa2q CZG1 KernelSU late-load diagnostics.
# Assumes bootstrap root is already available through the Root-My-Galaxy helper.

set -u

HELPER="${1:-/data/local/tmp/ksu-helper}"
KSUD="${2:-/data/local/tmp/ksud-s25u-kdp}"
STAGE="${3:-/data/local/tmp/.ksud-stage}"
OUT="${4:-/data/local/tmp/ksu-late-load-diagnose.log}"

exec >"$OUT" 2>&1

echo "=== KSU late-load diagnostic start ==="
date 2>/dev/null || true
uname -a 2>/dev/null || true
getprop ro.product.model 2>/dev/null || true
getprop ro.product.device 2>/dev/null || true
getprop ro.build.display.id 2>/dev/null || true
getprop ro.build.fingerprint 2>/dev/null || true

echo
echo "=== files ==="
ls -l "$HELPER" "$KSUD" "$STAGE" 2>&1 || true
sha256sum "$HELPER" "$KSUD" "$STAGE" 2>&1 || true

echo
echo "=== bootstrap helper probe ==="
"$HELPER" -c 'id; echo "[probe] uid=$(id -u)"; cat /proc/sys/kernel/kptr_restrict 2>/dev/null; grep -i kernelsu /proc/modules 2>/dev/null || true' 2>&1
PROBE_RC=$?
echo "[diag] probe_rc=$PROBE_RC"

echo
echo "=== processes before late-load ==="
ps -A -o PID,PPID,USER,NAME,ARGS 2>/dev/null | grep -E 'ksu|ksud|cve43499|logcat' || true

echo
echo "=== late-load start ==="
START=$(date +%s 2>/dev/null || echo 0)
"$HELPER" --late-load &
LPID=$!
echo "[diag] helper_late_load_pid=$LPID"

SECOND=0
while kill -0 "$LPID" 2>/dev/null; do
    SECOND=$((SECOND + 1))
    echo "[diag] late-load alive t=${SECOND}s pid=$LPID"
    ps -A -o PID,PPID,USER,NAME,ARGS 2>/dev/null | grep -E 'ksu|ksud|cve43499|logcat' || true
    if [ "$SECOND" -ge 120 ]; then
        echo "[diag] timeout=120s helper still alive; sending TERM"
        kill "$LPID" 2>/dev/null || true
        sleep 2
        kill -9 "$LPID" 2>/dev/null || true
        break
    fi
    sleep 1
done

wait "$LPID" 2>/dev/null
LATE_RC=$?
END=$(date +%s 2>/dev/null || echo 0)
echo "[diag] late_load_rc=$LATE_RC elapsed=$((END - START))s"

echo
echo "=== processes after late-load ==="
ps -A -o PID,PPID,USER,NAME,ARGS 2>/dev/null | grep -E 'ksu|ksud|cve43499|logcat' || true

echo
echo "=== module state ==="
"$HELPER" -c 'echo "--- /proc/modules ---"; grep -i kernelsu /proc/modules 2>/dev/null || true; echo "--- kptr_restrict ---"; cat /proc/sys/kernel/kptr_restrict 2>/dev/null; echo "--- dmesg tail ---"; dmesg 2>/dev/null | tail -200' 2>&1 || true

echo
echo "=== logcat tail ==="
logcat -d -t 300 2>/dev/null | grep -Ei 'kernelSU|ksud|late-load|lkm|insmod|module|avc|selinux' || true

echo
echo "=== diagnostic end ==="
echo "log=$OUT"
