"""Short mutation and worker-handoff gate shared with restart and directory changes."""
import threading

MUTEX = threading.RLock()
