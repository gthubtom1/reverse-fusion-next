"""Finite argv runner with owned descendant cleanup and elapsed/peak telemetry."""
import ctypes
import os
import signal
import subprocess
import time
import tempfile


def run_owned(argv, *, cwd, stdin: bytes, timeout: float, memory_mb: int | None = None,
              max_output_bytes: int = 16 * 1024 * 1024, env=None, cancel_event=None) -> dict:
    started = time.perf_counter()
    job, kernel = None, None
    process = None
    peak = None
    stdout_file, stderr_file, stdin_file = tempfile.TemporaryFile(), tempfile.TemporaryFile(), tempfile.TemporaryFile()
    stdin_file.write(stdin); stdin_file.seek(0)
    try:
        if os.name == 'nt':
            from ctypes import wintypes as w
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
            kernel.CreateJobObjectW.restype = w.HANDLE
            kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
            kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
            kernel.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
            kernel.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
            kernel.CloseHandle.argtypes = [w.HANDLE]

            class Basic(ctypes.Structure):
                _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                            ('flags', w.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                            ('active', w.DWORD), ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
            class Counters(ctypes.Structure):
                _fields_ = [(key, ctypes.c_ulonglong) for key in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
            class Limits(ctypes.Structure):
                _fields_ = [('basic', Basic), ('io', Counters), ('process_limit', ctypes.c_size_t),
                            ('job_limit', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
            job = kernel.CreateJobObjectW(None, None)
            if not job:
                raise ctypes.WinError(ctypes.get_last_error())
            limits = Limits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if memory_mb:
                limits.basic.flags |= 0x200  # JOB_OBJECT_LIMIT_JOB_MEMORY
                limits.job_limit = memory_mb * 1024 * 1024
            if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=stdin_file, stdout=stdout_file,
                stderr=stderr_file, creationflags=subprocess.CREATE_NO_WINDOW | 0x4)  # suspended until contained
            if not kernel.AssignProcessToJobObject(job, int(process._handle)):
                process.kill(); process.communicate()
                raise ctypes.WinError(ctypes.get_last_error())
            native = ctypes.WinDLL('ntdll')
            native.NtResumeProcess.argtypes = [w.HANDLE]
            native.NtResumeProcess.restype = ctypes.c_long
            if native.NtResumeProcess(int(process._handle)) != 0:
                raise OSError('Cannot resume contained process')
        else:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=stdin_file, stdout=stdout_file,
                                       stderr=stderr_file, start_new_session=True)
        timed_out, output_exceeded, cancelled = False, False, False
        deadline = time.monotonic() + timeout
        while True:
            try:
                process.communicate(timeout=min(.1, max(.001, deadline-time.monotonic())))
                break
            except subprocess.TimeoutExpired:
                output_exceeded = any(os.fstat(stream.fileno()).st_size > max_output_bytes for stream in (stdout_file, stderr_file))
                timed_out = time.monotonic() >= deadline
                cancelled = bool(cancel_event and cancel_event.is_set())
                if not output_exceeded and not timed_out and not cancelled:
                    continue
                if job:
                    if not kernel.TerminateJobObject(job, 124):
                        raise ctypes.WinError(ctypes.get_last_error())
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=5)
                break
        if job:
            if not kernel.TerminateJobObject(job, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            measured = Limits()
            if kernel.QueryInformationJobObject(job, 9, ctypes.byref(measured), ctypes.sizeof(measured), None):
                peak = measured.peak_job
        stdout_file.seek(0); stderr_file.seek(0)
        stdout, stderr = stdout_file.read(max_output_bytes + 1), stderr_file.read(max_output_bytes + 1)
        limited = output_exceeded or len(stdout) > max_output_bytes or len(stderr) > max_output_bytes
        return {'status': 'unknown' if timed_out or limited or cancelled else 'observed',
                'reason': 'cancelled' if cancelled else 'timeout' if timed_out else 'output-limit' if limited else None,
                'exit_code': process.returncode, 'stdout': stdout, 'stderr': stderr,
                'elapsed_ms': round((time.perf_counter() - started) * 1000, 3),
                'peak_job_bytes': peak,
                'output_truncated': limited,
                'memory_limit_mb': memory_mb if os.name == 'nt' else None,
                'cleanup': 'owned Windows job closed after invocation' if job else 'owned process group terminated after invocation'}
    finally:
        if job:
            kernel.CloseHandle(job)  # closes any still-running owned descendants, including on exceptions
        elif process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
        stdout_file.close(); stderr_file.close(); stdin_file.close()
