from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise SystemExit(f"{label}: anchor not found")


vm = Path("app/src/main/java/dev/busung/s25uroot/InstallViewModel.kt")
text = vm.read_text()

old_kptr = '''            echo "[ksu-prep] kptr_restrict=$value"
            [ "$value" = "1" ] || exit 43'''
new_kptr = '''            echo "[ksu-prep] kptr_restrict=${'$'}value"
            [ "${'$'}value" = "1" ] || exit 43'''
text = replace_once(text, old_kptr, new_kptr, "kptr shell interpolation")

old_install = '''        appendLog("[+] KSU_POST_STAGE_SETTLE_DONE")
        appendLog("[*] KSU_LATE_LOAD_START")
        val lateLoad = runHelper("--late-load")
        appendLog("[*] KSU_LATE_LOAD_RETURN rc=${lateLoad.code}")
        require(lateLoad.code == 0) {
            app.getString(R.string.error_ksu_verify, lateLoad.code, lateLoad.output)
        }
        if (lateLoad.output.isNotBlank()) appendLog(lateLoad.output)
        storeInstallReceipt()
        appendLog(app.getString(R.string.log_ksu_control_verified))'''

new_install = '''        appendLog("[+] KSU_POST_STAGE_SETTLE_DONE")
        val stageBefore = runHelper(
            "-c",
            "/system/bin/ls -l $SHIZUKU_KSUD_PATH $SHIZUKU_KSUD_STAGE_PATH /data/adb/ksud 2>&1 || true",
        )
        appendLog("[*] KSU_LATE_LOAD_STAGE_BEFORE rc=${stageBefore.code}")
        if (stageBefore.output.isNotBlank()) appendLog(stageBefore.output)

        appendLog("[*] KSU_LATE_LOAD_START")
        val lateLoad = runHelper("--late-load")
        appendLog("[*] KSU_LATE_LOAD_RETURN rc=${lateLoad.code}")
        require(lateLoad.code == 0) {
            app.getString(R.string.error_ksu_verify, lateLoad.code, lateLoad.output)
        }
        if (lateLoad.output.isNotBlank()) appendLog(lateLoad.output)

        val stageAfter = runHelper(
            "-c",
            "/system/bin/ls -l $SHIZUKU_KSUD_PATH $SHIZUKU_KSUD_STAGE_PATH /data/adb/ksud 2>&1 || true",
        )
        appendLog("[*] KSU_LATE_LOAD_STAGE_AFTER rc=${stageAfter.code}")
        if (stageAfter.output.isNotBlank()) appendLog(stageAfter.output)

        storeInstallReceipt()
        appendLog(app.getString(R.string.log_ksu_control_verified))'''
text = replace_once(text, old_install, new_install, "installKernelSu late-load diagnostics")

old_helper = '''    private suspend fun runHelper(vararg arguments: String): CommandResult {
        val helper = helperFile()
        val process = if (shizukuEnabled()) {
            ShizukuController.exec(arrayOf(helper.absolutePath) + arguments)
        } else {
            ProcessBuilder(listOf(helper.absolutePath) + arguments)
                .redirectErrorStream(true)
                .start()
        }
        val captured = StringBuilder()
        val startedAt = SystemClock.elapsedRealtime()
        try {
            while (process.isAlive) {
                drainProcessOutput(process, captured)
                require(SystemClock.elapsedRealtime() - startedAt < HELPER_TIMEOUT_MILLIS) {
                    app.getString(
                        R.string.error_helper_timeout,
                        captured.toString().trim().takeIf(String::isNotBlank)
                            ?.let { ": $it" } ?: "",
                    )
                }
                delay(HELPER_POLL_INTERVAL)
            }
            drainProcessOutput(process, captured)
            val exitCode = process.waitFor()
            return CommandResult(exitCode, stripAnsi(captured.toString().trim()))
        } finally {
            if (process.isAlive) {
                process.destroy()
                delay(500.milliseconds)
                if (process.isAlive) process.destroyForcibly()
            }
        }
    }'''

new_helper = '''    private suspend fun runHelper(vararg arguments: String): CommandResult {
        val helper = helperFile()
        val isLateLoad = arguments.size == 1 && arguments[0] == "--late-load"
        if (isLateLoad) {
            appendLog(
                "[*] KSU_LATE_LOAD_EXEC helper=${helper.absolutePath} " +
                    "shizuku=${if (shizukuEnabled()) "ON" else "OFF"}",
            )
        }
        val process = if (shizukuEnabled()) {
            ShizukuController.exec(arrayOf(helper.absolutePath) + arguments)
        } else {
            ProcessBuilder(listOf(helper.absolutePath) + arguments)
                .redirectErrorStream(true)
                .start()
        }
        if (isLateLoad) {
            val pid = runCatching { process.pid() }.getOrDefault(-1L)
            appendLog("[*] KSU_LATE_LOAD_PID pid=$pid")
        }
        val captured = StringBuilder()
        val startedAt = SystemClock.elapsedRealtime()
        var publishedLength = 0
        var lastHeartbeatAt = startedAt
        try {
            while (process.isAlive) {
                drainProcessOutput(process, captured)
                if (isLateLoad && captured.length > publishedLength) {
                    val delta = stripAnsi(captured.substring(publishedLength)).trim()
                    publishedLength = captured.length
                    if (delta.isNotBlank()) appendLog(delta)
                }
                val now = SystemClock.elapsedRealtime()
                if (isLateLoad && now - lastHeartbeatAt >= HELPER_HEARTBEAT_MILLIS) {
                    appendLog(
                        "[*] KSU_LATE_LOAD_WAIT elapsed_ms=${now - startedAt} " +
                            "captured_chars=${captured.length}",
                    )
                    lastHeartbeatAt = now
                }
                require(now - startedAt < HELPER_TIMEOUT_MILLIS) {
                    app.getString(
                        R.string.error_helper_timeout,
                        captured.toString().trim().takeIf(String::isNotBlank)
                            ?.let { ": $it" } ?: "",
                    )
                }
                delay(HELPER_POLL_INTERVAL)
            }
            drainProcessOutput(process, captured)
            if (isLateLoad && captured.length > publishedLength) {
                val delta = stripAnsi(captured.substring(publishedLength)).trim()
                publishedLength = captured.length
                if (delta.isNotBlank()) appendLog(delta)
            }
            val exitCode = process.waitFor()
            if (isLateLoad) {
                appendLog(
                    "[*] KSU_LATE_LOAD_HELPER_EXIT rc=$exitCode " +
                        "elapsed_ms=${SystemClock.elapsedRealtime() - startedAt}",
                )
            }
            return CommandResult(exitCode, stripAnsi(captured.toString().trim()))
        } finally {
            if (process.isAlive) {
                if (isLateLoad) {
                    appendLog(
                        "[!] KSU_LATE_LOAD_HELPER_TERMINATING " +
                            "elapsed_ms=${SystemClock.elapsedRealtime() - startedAt}",
                    )
                }
                process.destroy()
                delay(500.milliseconds)
                if (process.isAlive) {
                    if (isLateLoad) appendLog("[!] KSU_LATE_LOAD_HELPER_FORCE_KILL")
                    process.destroyForcibly()
                }
            }
        }
    }'''
text = replace_once(text, old_helper, new_helper, "runHelper diagnostics")

old_const = "        private const val HELPER_TIMEOUT_MILLIS = 120_000L\n"
new_const = (
    "        private const val HELPER_TIMEOUT_MILLIS = 120_000L\n"
    "        private const val HELPER_HEARTBEAT_MILLIS = 5_000L\n"
)
text = replace_once(text, old_const, new_const, "late-load heartbeat constant")
vm.write_text(text)

gradle = Path("app/build.gradle.kts")
g = gradle.read_text()
if "versionCode = 14" in g:
    g = g.replace("versionCode = 14", "versionCode = 15", 1)
elif "versionCode = 15" not in g:
    raise SystemExit("versionCode anchor not found")

if 'versionName = "0.2.66"' in g:
    g = g.replace('versionName = "0.2.66"', 'versionName = "0.2.67-s9360diag1"', 1)
elif 'versionName = "0.2.67-s9360diag1"' not in g:
    raise SystemExit("versionName anchor not found")

gradle.write_text(g)
