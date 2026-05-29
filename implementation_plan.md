# Windows-Optimized HR Screening Tool v2

Create `hr_screening_tool_v2_win.py` — a Windows-optimized fork of [hr_screening_tool_v2.py](file:///Users/admin/Documents/Project_HR_Screening_Prototypes/hr_screening_tool_v2.py) that preserves every feature while delivering better performance and reliability on Windows.

## Why a Separate File

The original is tuned for macOS (MPS/Apple GPU, macOS path conventions, emoji reliance). Rather than adding `if sys.platform` branches everywhere, a clean Windows-targeted file is more maintainable and lets us apply Windows-specific optimizations without compromise.

## Proposed Changes

### 1. Process-Based Parallelism (biggest perf win)

> [!IMPORTANT]
> On Windows, Python's `threading` with `ThreadPoolExecutor` gives **zero** CPU parallelism due to the GIL. The original uses threads, which on macOS works acceptably because the heavy work is `subprocess.run()` (I/O-bound). But on Windows, subprocess spawning is significantly slower, making thread overhead more noticeable.

**Change:** Replace `ThreadPoolExecutor` with `ProcessPoolExecutor` using `concurrent.futures`, and guard everything with `if __name__ == "__main__"` (required on Windows for multiprocessing).

- All shared state (tracking file) will use file-based locking instead of `threading.Lock`
- The converter object (Docling) cannot be pickled across processes, so each worker process will build its own converter instance (one-time cost per worker, amortized over the batch)

### 2. Async Subprocess Calls with `asyncio`

**Change:** Replace `subprocess.run()` + `time.sleep()` with `asyncio.create_subprocess_exec()` + `asyncio.sleep()`.

- On Windows, `asyncio` uses IOCP (I/O Completion Ports) — the fastest async I/O mechanism available on the platform
- This eliminates blocking waits during `REQUEST_DELAY` and `SUB_BATCH_PAUSE` — the event loop can do useful work instead of sleeping
- Retry backoff becomes non-blocking
- Multiple Claude CLI calls can be in-flight concurrently using `asyncio.Semaphore` to respect rate limits

### 3. Windows Terminal & Encoding Fixes

**Change:** Fix the common Windows pain points:

- Set `sys.stdout` and `sys.stderr` to UTF-8 at startup (Windows defaults to the system codepage, which breaks emoji and non-ASCII candidate names)
- Add `colorama.init()` fallback for ANSI color support on older Windows terminals (graceful — works without it)
- Replace problematic emoji with safer Unicode characters that render correctly in both Windows Terminal and legacy `cmd.exe`
- Set console title via `ctypes` for a polished feel

### 4. CUDA GPU Support (replaces MPS)

**Change:** Replace Apple MPS detection with NVIDIA CUDA detection:

- MPS is Apple-only — useless on Windows
- Detect `torch.cuda.is_available()` for NVIDIA GPUs
- Use `AcceleratorDevice('cuda')` for Docling when available
- Keep the same batch-threshold logic (GPU for large batches, CPU for small ones)
- Add DirectML fallback detection for AMD GPUs via `torch-directml` (optional)

### 5. Windows Path Handling

**Change:** Normalize all path operations:

- Use `pathlib.Path` throughout instead of `os.path.join()` for cleaner Windows path handling
- Handle long paths (>260 chars) by prefixing with `\\?\` when needed
- Use `os.fspath()` for Docling compatibility

### 6. File Locking for Concurrent Safety

**Change:** Replace `threading.Lock` with proper file locking:

- Use `msvcrt.locking()` (Windows-native) for the tracking JSON file
- Prevents corruption when multiple processes write simultaneously
- Wrapped in a context manager for clean usage

### 7. Process Priority & Console Handling

**Change:** Add Windows-specific process optimizations:

- Set process priority to `ABOVE_NORMAL` during batch processing for better responsiveness
- Register `CTRL+C` handler via `signal` for clean shutdown (Windows doesn't handle `KeyboardInterrupt` in subprocesses the same way as Unix)
- Graceful interrupt: on `Ctrl+C`, finish current resume, save progress, then exit

---

## Feature Parity Checklist

Every feature from the original will be preserved:

| Feature | Status |
|---|---|
| Screen new resumes (skip cached) | ✅ Preserved |
| Re-analyze all resumes | ✅ Preserved |
| Re-analyze specific resume | ✅ Preserved |
| Write job description | ✅ Preserved |
| Phone screening questions | ✅ Preserved |
| View screening history | ✅ Preserved |
| Maintenance (delete JD/resumes) | ✅ Preserved |
| PDF extraction via Docling | ✅ Preserved |
| PDF quality rating | ✅ Preserved |
| Tracking/caching system | ✅ Preserved (same JSON format) |
| Rate limiting & backoff | ✅ Preserved (now async) |
| Sub-batch processing | ✅ Preserved |
| Token estimation | ✅ Preserved |
| Back-navigation (`b`) | ✅ Preserved |

> [!NOTE]
> The tracking file format (`screening_history_v2.json`) is identical — you can share tracking data between the macOS and Windows versions.

---

## Summary of File

#### [NEW] [hr_screening_tool_v2_win.py](file:///Users/admin/Documents/Project_HR_Screening_Prototypes/hr_screening_tool_v2_win.py)

Single new file containing the full Windows-optimized tool.

---

## Verification Plan

### Automated Tests
- Run `python hr_screening_tool_v2_win.py` and verify the main menu renders with correct characters (no garbled emoji)
- Verify `claude` CLI detection works via `shutil.which("claude")`
- Confirm CUDA detection path (graceful fallback to CPU if no GPU)

### Manual Verification
- User tests on their Windows machine with real resumes and JDs
- Confirm CSV output in `results/` folder matches expected format
