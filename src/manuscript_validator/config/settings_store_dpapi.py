"""Windows DPAPI secret box -- production (Task 15).

`import win32crypt` is deliberately lazy, inside the methods: that is what lets
this module be imported and its non-DPAPI logic tested on the Linux dev box.

Uses app-specific entropy and per-user protection (`flags=0`); never
CRYPTPROTECT_LOCAL_MACHINE, which would let any user on the machine decrypt.
"""
