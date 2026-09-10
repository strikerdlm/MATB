"""Send real browser zoom shortcuts through XTest to an isolated Xvfb display."""
import ctypes as c
import ctypes.util
import time

x = c.CDLL(ctypes.util.find_library("X11"))
t = c.CDLL(ctypes.util.find_library("Xtst"))
x.XOpenDisplay.argtypes = [c.c_char_p]
x.XOpenDisplay.restype = c.c_void_p
x.XDefaultRootWindow.argtypes = [c.c_void_p]
x.XDefaultRootWindow.restype = c.c_ulong
x.XQueryTree.argtypes = [c.c_void_p, c.c_ulong, c.POINTER(c.c_ulong), c.POINTER(c.c_ulong), c.POINTER(c.POINTER(c.c_ulong)), c.POINTER(c.c_uint)]
x.XGetGeometry.argtypes = [c.c_void_p, c.c_ulong, c.POINTER(c.c_ulong), c.POINTER(c.c_int), c.POINTER(c.c_int), c.POINTER(c.c_uint), c.POINTER(c.c_uint), c.POINTER(c.c_uint), c.POINTER(c.c_uint)]
x.XSetInputFocus.argtypes = [c.c_void_p, c.c_ulong, c.c_int, c.c_ulong]
x.XKeysymToKeycode.argtypes = [c.c_void_p, c.c_ulong]
x.XKeysymToKeycode.restype = c.c_ubyte
x.XFlush.argtypes = [c.c_void_p]
x.XFree.argtypes = [c.c_void_p]
x.XCloseDisplay.argtypes = [c.c_void_p]
t.XTestFakeKeyEvent.argtypes = [c.c_void_p, c.c_uint, c.c_int, c.c_ulong]
d = x.XOpenDisplay(None)
assert d, "Xvfb display is unavailable"
root, parent, children, count = c.c_ulong(), c.c_ulong(), c.POINTER(c.c_ulong)(), c.c_uint()
x.XQueryTree(d, x.XDefaultRootWindow(d), c.byref(root), c.byref(parent), c.byref(children), c.byref(count))
windows = []
for i in range(count.value):
    r, px, py, w, h, border, depth = c.c_ulong(), c.c_int(), c.c_int(), c.c_uint(), c.c_uint(), c.c_uint(), c.c_uint()
    if x.XGetGeometry(d, children[i], c.byref(r), c.byref(px), c.byref(py), c.byref(w), c.byref(h), c.byref(border), c.byref(depth)):
        windows.append((w.value * h.value, children[i]))
assert windows, "No browser window on isolated display"
x.XSetInputFocus(d, max(windows)[1], 2, 0)
x.XFree(children)
x.XFlush(d)

def key(symbol, down):
    t.XTestFakeKeyEvent(d, x.XKeysymToKeycode(d, symbol), int(down), 0)
    x.XFlush(d)
    time.sleep(0.06)

# Reset real browser zoom, then 110%, 125%, 150%, 175%, 200%.
key(0xFFE3, True)
key(ord("0"), True)
key(ord("0"), False)
key(0xFFE3, False)
for _ in range(5):
    key(0xFFE3, True)
    key(0xFFE1, True)
    key(ord("="), True)
    key(ord("="), False)
    key(0xFFE1, False)
    key(0xFFE3, False)
x.XCloseDisplay(d)
