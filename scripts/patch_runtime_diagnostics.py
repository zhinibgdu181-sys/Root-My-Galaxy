#!/usr/bin/env python3
from pathlib import Path

VM = Path("app/src/main/java/dev/busung/s25uroot/InstallViewModel.kt")
ACTIVITY = Path("app/src/main/java/dev/busung/s25uroot/InstallActivity.kt")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_view_model() -> None:
    text = VM.read_text()

    text = replace_once(
        text,
        "import android.app.Application\n",
        "import android.app.Application\n"
        "import android.content.ContentValues\n"
        "import android.net.Uri\n"
        "import android.os.Environment\n"
        "import android.provider.MediaStore\n",
        "viewmodel imports",
    )
    text = replace_once(
        text,
        "import java.io.File\nimport java.io.InputStream\n",
        "import java.io.File\nimport java.io.FileOutputStream\nimport java.io.InputStream\n",
        "file output import",
    )
    text = replace_once(
        text,
        "    private var activeHistoryEntry: InstallHistoryEntry? = null\n",
        "    private var activeHistoryEntry: InstallHistoryEntry? = null\n"
        "    private var activeCrashLogUri: Uri? = null\n",
        "crash log uri field",
    )
    text = replace_once(
        text,
        '        val lateLoad = runHelper("--late-load")\n',
        '        val lateLoad = runLateLoadWithDiagnostics()\n',
        "late-load call",
    )

    run_late_load = r'''    private suspend fun runLateLoadWithDiagnostics(): CommandResult {
        val helper = helperFile()
        appendLog(
            "[*] KSU_LATE_LOAD_EXEC helper=${helper.absolutePath} " +
                "shizuku=${if (shizukuEnabled()) "ON" else "OFF"}",
        )
        val process = if (shizukuEnabled()) {
            ShizukuController.exec(arrayOf(helper.absolutePath, "--late-load"))
        } else {
            ProcessBuilder(helper.absolutePath, "--late-load")
                .redirectErrorStream(true)
                .start()
        }
        val captured = StringBuilder()
        val startedAt = SystemClock.elapsedRealtime()
        var reportedLength = 0
        var lastHeartbeatAt = startedAt
        try {
            while (process.isAlive) {
                drainProcessOutput(process, captured)
                if (captured.length > reportedLength) {
                    val delta = stripAnsi(captured.substring(reportedLength)).trim()
                    if (delta.isNotBlank()) appendLog("[ksud] $delta")
                    reportedLength = captured.length
                }
                val now = SystemClock.elapsedRealtime()
                if (now - lastHeartbeatAt >= KSU_LATE_LOAD_HEARTBEAT_MILLIS) {
                    appendLog(
                        "[*] KSU_LATE_LOAD_WAIT elapsed=${(now - startedAt) / 1000}s " +
                            "output_bytes=${captured.length}",
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
            if (captured.length > reportedLength) {
                val delta = stripAnsi(captured.substring(reportedLength)).trim()
                if (delta.isNotBlank()) appendLog("[ksud] $delta")
            }
            return CommandResult(process.waitFor(), stripAnsi(captured.toString().trim()))
        } finally {
            if (process.isAlive) {
                process.destroy()
                delay(500.milliseconds)
                if (process.isAlive) process.destroyForcibly()
            }
        }
    }

'''
    text = replace_once(
        text,
        "    private fun shellQuote(value: String) =",
        run_late_load + "    private fun shellQuote(value: String) =",
        "late-load diagnostics function",
    )

    text = replace_once(
        text,
        "        updateHistoryLog()\n    }\n\n    private suspend fun installKernelSu",
        "        updateHistoryLog()\n        persistCrashSafeLog()\n    }\n\n    private suspend fun installKernelSu",
        "persist exploit log",
    )
    text = replace_once(
        text,
        "        updateHistoryLog()\n    }\n\n    private fun startHistory()",
        "        updateHistoryLog()\n        persistCrashSafeLog()\n    }\n\n    private fun startHistory()",
        "persist append log",
    )
    text = replace_once(
        text,
        "    private fun startHistory() {\n        val entry = historyStore.create()\n        activeHistoryEntry = entry\n        publishHistory(entry)\n    }\n",
        "    private fun startHistory() {\n"
        "        val entry = historyStore.create()\n"
        "        activeHistoryEntry = entry\n"
        "        activeCrashLogUri = createCrashSafeLog(entry)\n"
        "        persistCrashSafeLog()\n"
        "        publishHistory(entry)\n"
        "    }\n\n"
        "    private fun createCrashSafeLog(entry: InstallHistoryEntry): Uri? = runCatching {\n"
        "        val values = ContentValues().apply {\n"
        "            put(MediaStore.Downloads.DISPLAY_NAME, \"RootMyGalaxy-live-${entry.startedAtMillis}.log\")\n"
        "            put(MediaStore.Downloads.MIME_TYPE, \"text/plain\")\n"
        "            put(\n"
        "                MediaStore.Downloads.RELATIVE_PATH,\n"
        "                Environment.DIRECTORY_DOWNLOADS + \"/RootMyGalaxy\",\n"
        "            )\n"
        "        }\n"
        "        app.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)\n"
        "    }.getOrNull()\n\n"
        "    private fun persistCrashSafeLog() {\n"
        "        val uri = activeCrashLogUri ?: return\n"
        "        val bytes = mutableState.value.log.toByteArray(Charsets.UTF_8)\n"
        "        runCatching {\n"
        "            app.contentResolver.openFileDescriptor(uri, \"rwt\")?.use { descriptor ->\n"
        "                FileOutputStream(descriptor.fileDescriptor).use { output ->\n"
        "                    output.write(bytes)\n"
        "                    output.flush()\n"
        "                    output.fd.sync()\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "    }\n",
        "crash-safe Downloads log",
    )
    text = replace_once(
        text,
        "        activeHistoryEntry = null\n    }\n\n    private fun publishHistory",
        "        persistCrashSafeLog()\n        activeHistoryEntry = null\n        activeCrashLogUri = null\n    }\n\n    private fun publishHistory",
        "final crash log flush",
    )
    text = replace_once(
        text,
        "        private const val HELPER_TIMEOUT_MILLIS = 120_000L\n",
        "        private const val HELPER_TIMEOUT_MILLIS = 120_000L\n"
        "        private const val KSU_LATE_LOAD_HEARTBEAT_MILLIS = 5_000L\n",
        "heartbeat constant",
    )

    VM.write_text(text)


def patch_install_activity() -> None:
    text = ACTIVITY.read_text()
    text = replace_once(
        text,
        "import android.view.WindowManager\n",
        "import android.view.WindowManager\nimport android.widget.Toast\n",
        "toast import",
    )
    text = replace_once(
        text,
        "import androidx.activity.compose.BackHandler\n",
        "import androidx.activity.compose.BackHandler\nimport androidx.activity.compose.rememberLauncherForActivityResult\n",
        "launcher compose import",
    )
    text = replace_once(
        text,
        "import androidx.activity.result.contract.ActivityResultContracts\n" if "import androidx.activity.result.contract.ActivityResultContracts\n" in text else "import androidx.activity.viewModels\n",
        "import androidx.activity.result.contract.ActivityResultContracts\nimport androidx.activity.viewModels\n"
        if "import androidx.activity.result.contract.ActivityResultContracts\n" not in text else
        "import androidx.activity.result.contract.ActivityResultContracts\n",
        "activity result import",
    )
    text = replace_once(
        text,
        "import androidx.compose.ui.platform.LocalView\n",
        "import androidx.compose.ui.platform.LocalContext\nimport androidx.compose.ui.platform.LocalView\n",
        "local context import",
    )
    text = replace_once(
        text,
        "    val logScrollState = rememberScrollState()\n    val view = LocalView.current\n",
        "    val logScrollState = rememberScrollState()\n"
        "    val view = LocalView.current\n"
        "    val context = LocalContext.current\n"
        "    val exportLogLauncher = rememberLauncherForActivityResult(\n"
        "        ActivityResultContracts.CreateDocument(\"text/plain\"),\n"
        "    ) { uri ->\n"
        "        if (uri != null) {\n"
        "            val saved = runCatching {\n"
        "                context.contentResolver.openOutputStream(uri)?.use { output ->\n"
        "                    output.write(installState.log.toByteArray(Charsets.UTF_8))\n"
        "                    output.flush()\n"
        "                } ?: error(\"open failed\")\n"
        "            }.isSuccess\n"
        "            Toast.makeText(\n"
        "                context,\n"
        "                context.getString(if (saved) R.string.export_log_saved else R.string.export_log_failed),\n"
        "                Toast.LENGTH_LONG,\n"
        "            ).show()\n"
        "        }\n"
        "    }\n",
        "live export launcher",
    )
    text = replace_once(
        text,
        "            InstallerSteps(installState.phase)\n            InstallerLog(\n",
        "            InstallerSteps(installState.phase)\n"
        "            FilledTonalButton(\n"
        "                onClick = {\n"
        "                    clickHaptic(view)\n"
        "                    exportLogLauncher.launch(\n"
        "                        \"RootMyGalaxy-live-${System.currentTimeMillis()}.log\",\n"
        "                    )\n"
        "                },\n"
        "                modifier = Modifier.fillMaxWidth(),\n"
        "            ) {\n"
        "                Text(stringResource(R.string.export_log))\n"
        "            }\n"
        "            InstallerLog(\n",
        "live save button",
    )
    ACTIVITY.write_text(text)


patch_view_model()
patch_install_activity()
print("Applied runtime diagnostics, crash-safe Downloads log, and live log export")
