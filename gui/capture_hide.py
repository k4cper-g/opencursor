"""Platform-specific window capture hiding."""

import sys


def hide_from_capture(window_id: int) -> bool:
    """Hide a window from screen capture. Returns True if successful."""
    if sys.platform == "win32":
        return _hide_windows(window_id)
    elif sys.platform == "darwin":
        return _hide_macos(window_id)
    else:
        print("WARNING: Capture hiding not supported on this platform")
        return False


def show_in_capture(window_id: int) -> bool:
    """Remove capture hiding so the window appears in screenshots again."""
    if sys.platform == "win32":
        return _show_windows(window_id)
    elif sys.platform == "darwin":
        return _show_macos(window_id)
    else:
        return False


def _hide_windows(hwnd: int) -> bool:
    """Windows: SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)."""
    import ctypes

    WDA_EXCLUDEFROMCAPTURE = 0x00000011
    WDA_MONITOR = 0x00000001
    user32 = ctypes.windll.user32

    if user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
        return True
    if user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR):
        print("WARNING: Using WDA_MONITOR fallback (overlay will appear black in captures)")
        return True
    print(f"WARNING: SetWindowDisplayAffinity failed (error {ctypes.GetLastError()})")
    return False


def _show_windows(hwnd: int) -> bool:
    """Windows: SetWindowDisplayAffinity(WDA_NONE) — visible in captures."""
    import ctypes
    WDA_NONE = 0x00000000
    return bool(ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_NONE))


def _hide_macos(window_id: int) -> bool:
    """macOS: NSWindow.setSharingType(.none) via PyObjC. Best-effort."""
    try:
        import objc
        from ctypes import c_void_p

        # PySide6 winId() on macOS returns an NSView pointer
        view = objc.objc_object(c_void_p=c_void_p(window_id))
        ns_window = view.window()
        if ns_window:
            ns_window.setSharingType_(0)  # NSWindowSharingNone
            return True
        print("WARNING: Could not get NSWindow from view")
        return False
    except ImportError:
        print("WARNING: PyObjC not installed; capture hiding unavailable on macOS")
        print("  Install with: pip install pyobjc-framework-Cocoa")
        return False
    except Exception as e:
        print(f"WARNING: macOS capture hiding failed: {e}")
        return False


def _show_macos(window_id: int) -> bool:
    """macOS: NSWindow.setSharingType(.readOnly) — visible in captures."""
    try:
        import objc
        from ctypes import c_void_p

        view = objc.objc_object(c_void_p=c_void_p(window_id))
        ns_window = view.window()
        if ns_window:
            ns_window.setSharingType_(1)  # NSWindowSharingReadOnly
            return True
        return False
    except Exception:
        return False
