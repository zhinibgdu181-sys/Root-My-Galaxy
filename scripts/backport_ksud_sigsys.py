#!/usr/bin/env python3
"""Minimal backport of tiann/KernelSU 35feb588 to the pinned v3.2.5 ksud.

This intentionally leaves the Samsung-patched kernel module unchanged. It only
prevents ksud/Manager helper processes from being killed when Android seccomp
traps the legacy magic reboot syscall used for KernelSU driver-fd discovery.
"""

from pathlib import Path
import re
import sys


root = Path(sys.argv[1] if len(sys.argv) > 1 else "KernelSU")
cli = root / "userspace/ksud/src/cli.rs"
calls = root / "userspace/ksud/src/ksucalls.rs"

# cli.rs: install the handler before any command can probe the KernelSU driver.
s = cli.read_text()
if "ksucalls::setup_sigsys_handler();" not in s:
    pat = re.compile(
        r'(    android_logger::init_once\(\n'
        r'.*?'
        r'        \.with_tag\("KernelSU"\),\n'
        r'    \);\n)',
        re.DOTALL,
    )
    s, count = pat.subn(
        r'\1\n'
        r'    // Backport of tiann/KernelSU 35feb588: survive Samsung seccomp.\n'
        r'    ksucalls::setup_sigsys_handler();\n',
        s,
        count=1,
    )
    if count != 1:
        raise SystemExit("cli.rs logger insertion point not found")
    cli.write_text(s)

# ksucalls.rs: add the handler and guard only the legacy magic SVC probe.
s = calls.read_text()
if "use std::cell::Cell;" not in s:
    needle = "use crate::ksu_uapi;\n"
    if needle not in s:
        raise SystemExit("ksucalls.rs import insertion point not found")
    s = s.replace(needle, needle + "use std::cell::Cell;\n", 1)

if "pub fn setup_sigsys_handler()" not in s:
    marker = "// Global driver fd cache\n"
    if marker not in s:
        raise SystemExit("ksucalls.rs driver marker not found")

    handler = r'''// Backport of tiann/KernelSU commit 35feb58872b6f88ac1b488ce46a68892a017d62d.
// Samsung/Android seccomp may return SIGSYS (SYS_SECCOMP) for the legacy
// magic reboot syscall. Convert only an in-flight KernelSU SVC probe into
// -EPERM instead of letting the process die.
std::thread_local! {
    static SVC_IN_FLIGHT: Cell<bool> = const { Cell::new(false) };
    static SIGSYS_OCCURRED: Cell<bool> = const { Cell::new(false) };
}

const SYS_SECCOMP: libc::c_int = 1;

fn with_svc_call<F, R>(call: F) -> R
where
    F: FnOnce() -> R,
{
    SVC_IN_FLIGHT.with(|in_flight| in_flight.set(true));
    let result = call();
    SVC_IN_FLIGHT.with(|in_flight| in_flight.set(false));
    result
}

fn take_sigsys_occurred() -> bool {
    SIGSYS_OCCURRED.with(|occurred| occurred.replace(false))
}

extern "C" fn sigsys_handler(
    _sig: libc::c_int,
    info: *mut libc::siginfo_t,
    ctx: *mut libc::c_void,
) {
    unsafe {
        if info.is_null() || ctx.is_null() || (*info).si_code != SYS_SECCOMP {
            return;
        }
        if SVC_IN_FLIGHT.with(Cell::get) {
            SIGSYS_OCCURRED.with(|occurred| occurred.set(true));
        }

        let ucontext = ctx.cast::<libc::ucontext_t>();
        #[cfg(target_arch = "aarch64")]
        {
            (*ucontext).uc_mcontext.regs[0] = (-libc::EPERM) as u64;
        }
        #[cfg(target_arch = "x86_64")]
        {
            let rax = libc::REG_RAX as usize;
            (*ucontext).uc_mcontext.gregs[rax] = i64::from(-libc::EPERM);
        }
    }
}

pub fn setup_sigsys_handler() {
    unsafe {
        let mut sa: libc::sigaction = std::mem::zeroed();
        sa.sa_flags = libc::SA_SIGINFO;
        sa.sa_sigaction = sigsys_handler as *const () as usize;
        libc::sigemptyset(std::ptr::addr_of_mut!(sa.sa_mask));
        if libc::sigaction(libc::SIGSYS, std::ptr::addr_of!(sa), std::ptr::null_mut()) != 0 {
            let error = std::io::Error::last_os_error();
            log::warn!("Failed to set SIGSYS handler: {error}");
        }
    }
}

'''
    s = s.replace(marker, handler + marker, 1)

if "with_svc_call(|| unsafe" not in s:
    call_pat = re.compile(
        r'        unsafe \{\n'
        r'            libc::syscall\(\n'
        r'                libc::SYS_reboot,\n'
        r'                ksu_uapi::KSU_INSTALL_MAGIC1,\n'
        r'                ksu_uapi::KSU_INSTALL_MAGIC2,\n'
        r'                0,\n'
        r'                &mut fd,\n'
        r'            \);\n'
        r'        \};\n'
    )
    replacement = '''        with_svc_call(|| unsafe {
            libc::syscall(
                libc::SYS_reboot,
                ksu_uapi::KSU_INSTALL_MAGIC1,
                ksu_uapi::KSU_INSTALL_MAGIC2,
                0,
                &mut fd,
            )
        });
        if take_sigsys_occurred() {
            eprintln!("KernelSU driver install syscall was blocked by seccomp");
            log::error!("KernelSU driver install syscall was blocked by seccomp");
        }
'''
    s, count = call_pat.subn(replacement, s, count=1)
    if count != 1:
        raise SystemExit("ksucalls.rs magic reboot call not found")

calls.write_text(s)

print("Applied ksud SIGSYS backport")
