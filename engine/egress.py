"""Airplane-mode checks for the Runner: what a mode's processes connect to, with the network left on.

"Airplane" is an intent, not a switch: everything the mode needs lives on this machine, so nothing it starts
calls an external service. The machine's network is never touched. Two checks make the intent hold:

1. proxy_env(): every step and service gets HTTP(S)_PROXY / ALL_PROXY pointing at a closed local port, and
   NO_PROXY for loopback, so any client that honours proxy settings fails fast instead of reaching out.
2. Monitor: while the mode runs, it polls the OS connection table for every process in the mode's process
   trees (the services and steps the Runner started, and their children) and records each TCP connection to
   an address that isn't loopback or in the mode's "offline_allow" list. Any such connection fails the mode.
   Windows: netstat -ano; Linux: /proc; elsewhere: lsof. Standard library only.

Limits, stated plainly: a connection that opens and closes between two polls can be missed (the proxy settings
still catch proxy-honouring clients); processes inside containers are not in the host's process tree, so a
container that pulls or phones home isn't seen here (docker_pull_problem() makes container starts use only
local images).
"""

import ipaddress
import os
import re
import subprocess
import sys
import threading

DEAD_PROXY = "http://127.0.0.1:9"  # the discard port: nothing listens there, so proxied calls fail at once
LOOPBACK_HOSTS = "localhost,127.0.0.1,::1"
IGNORED_STATES = {"LISTEN", "LISTENING", "TIME_WAIT", "CLOSE", "CLOSED"}


def proxy_env(allow_hosts=()) -> dict:
    no_proxy = ",".join([LOOPBACK_HOSTS, *allow_hosts])
    env = {}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        env[key] = env[key.lower()] = DEAD_PROXY
    env["NO_PROXY"] = env["no_proxy"] = no_proxy
    env["NODE_USE_ENV_PROXY"] = "1"  # Node's fetch honours the variables above only with this set
    return env


_CONTAINER_START = re.compile(r"\b(docker|podman)(?:-compose|\s+compose)?\b[^&|;]*?\b(up|run|create)\b")
_PULL_NEVER = re.compile(r"--pull[ =]never\b")


def docker_pull_problem(command: str):
    """None, or why an airplane-mode command could fetch a container image over the network."""
    if _CONTAINER_START.search(command) and not _PULL_NEVER.search(command):
        return ("starts containers without '--pull never': an image missing locally would be downloaded. Add "
                "--pull never (images are fetched by the e2e-prefetch mode)")
    return None


def allowed_networks(values) -> list:
    out = []
    for v in values or []:
        try:
            out.append(ipaddress.ip_network(str(v), strict=False))
        except ValueError:
            pass  # a host name: it only feeds NO_PROXY
    return out


def is_external(ip: str, allow: list) -> bool:
    ip = ip.strip("[]").split("%")[0]
    if ip in ("", "*"):
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if getattr(addr, "ipv4_mapped", None):
        addr = addr.ipv4_mapped
    if addr.is_loopback or addr.is_unspecified:
        return False
    return not any(addr in net for net in allow)


def split_endpoint(text: str):
    """'1.2.3.4:443' or '[::1]:5000' -> ('1.2.3.4', 443)."""
    host, _, port = text.rpartition(":")
    try:
        return host.strip("[]"), int(port)
    except ValueError:
        return host.strip("[]"), 0


# ---- process trees -------------------------------------------------------------------------------------------

def process_table() -> dict:
    """pid -> (parent pid, name) for every process this user can see."""
    if os.name == "nt":
        return _process_table_windows()
    if os.path.isdir("/proc/self"):
        return _process_table_proc()
    out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,comm="], capture_output=True, text=True).stdout
    table = {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            table[int(parts[0])] = (int(parts[1]), parts[2].strip() if len(parts) > 2 else "?")
    return table


def _process_table_windows() -> dict:
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    k32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:
        return {}
    table = {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            table[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile)
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return table


def _process_table_proc() -> dict:
    table = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", encoding="utf-8", errors="replace") as f:
                stat = f.read()
        except OSError:
            continue
        # pid (comm) state ppid ...: comm may hold spaces and parentheses, so split at the last ')'
        comm = stat[stat.find("(") + 1:stat.rfind(")")]
        rest = stat[stat.rfind(")") + 2:].split()
        if len(rest) > 1 and rest[1].isdigit():
            table[int(name)] = (int(rest[1]), comm)
    return table


def descendants(roots, table: dict) -> set:
    """The roots and every process below them in the table."""
    children = {}
    for pid, (ppid, _) in table.items():
        if pid != ppid:
            children.setdefault(ppid, []).append(pid)
    seen, stack = set(), [p for p in roots if p]
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        stack.extend(children.get(pid, []))
    return seen


# ---- connection tables ---------------------------------------------------------------------------------------

def parse_netstat(text: str) -> list:
    """Windows `netstat -ano` -> [(pid, remote ip, remote port, state)] for TCP lines."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 5 and parts[0].upper() == "TCP" and parts[4].isdigit():
            ip, port = split_endpoint(parts[2])
            out.append((int(parts[4]), ip, port, parts[3].upper()))
    return out


_TCP_STATES = {"01": "ESTABLISHED", "02": "SYN_SENT", "03": "SYN_RECV", "04": "FIN_WAIT1", "05": "FIN_WAIT2",
               "06": "TIME_WAIT", "07": "CLOSE", "08": "CLOSE_WAIT", "09": "LAST_ACK", "0A": "LISTEN",
               "0B": "CLOSING"}


def _hex_ip(text: str) -> str:
    raw = bytes.fromhex(text)
    if len(raw) == 4:
        return str(ipaddress.IPv4Address(raw[::-1]))
    words = b"".join(raw[i:i + 4][::-1] for i in range(0, 16, 4))  # four little-endian 32-bit words
    return str(ipaddress.IPv6Address(words))


def parse_proc_net_tcp(text: str) -> dict:
    """/proc/net/tcp or tcp6 -> {socket inode: (remote ip, remote port, state)}."""
    out = {}
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 10:
            continue
        rem_ip, _, rem_port = parts[2].partition(":")
        try:
            out[parts[9]] = (_hex_ip(rem_ip), int(rem_port, 16), _TCP_STATES.get(parts[3].upper(), parts[3]))
        except ValueError:
            continue
    return out


def parse_lsof(text: str) -> list:
    """`lsof -nP -iTCP -F pn`-free form: `lsof -nP -iTCP` lines -> [(pid, remote ip, remote port, state)]."""
    out = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 9 or not parts[1].isdigit() or "->" not in parts[8]:
            continue
        ip, port = split_endpoint(parts[8].split("->", 1)[1])
        state = parts[9].strip("()") if len(parts) > 9 else ""
        out.append((int(parts[1]), ip, port, state.upper()))
    return out


def connections(pids: set) -> list:
    """[(pid, remote ip, remote port, state)] for the given processes."""
    if not pids:
        return []
    if os.name == "nt":
        text = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, errors="replace").stdout
        return [c for c in parse_netstat(text) if c[0] in pids]
    if os.path.isdir("/proc/self"):
        sockets = {}
        for fam in ("tcp", "tcp6"):
            try:
                with open(f"/proc/net/{fam}", encoding="ascii", errors="replace") as f:
                    sockets.update(parse_proc_net_tcp(f.read()))
            except OSError:
                pass
        out = []
        for pid in pids:
            try:
                fds = os.listdir(f"/proc/{pid}/fd")
            except OSError:
                continue
            for fd in fds:
                try:
                    target = os.readlink(f"/proc/{pid}/fd/{fd}")
                except OSError:
                    continue
                if target.startswith("socket:[") and target[8:-1] in sockets:
                    out.append((pid, *sockets[target[8:-1]]))
        return out
    text = subprocess.run(["lsof", "-nP", "-a", "-iTCP", "-p", ",".join(str(p) for p in pids)],
                          capture_output=True, text=True, errors="replace").stdout
    return [c for c in parse_lsof(text) if c[0] in pids]


def external(conns: list, allow: list) -> list:
    return [c for c in conns if c[3] not in IGNORED_STATES and is_external(c[1], allow)]


class Monitor:
    """Polls the connection table for the watched process trees until stopped; records external connections."""

    def __init__(self, allow=(), interval_s: float = 0.5, table=process_table, conns=connections):
        self.allow = allowed_networks(allow)
        self.interval_s = interval_s
        self._table, self._conns = table, conns
        self._roots = {}  # pid -> label (the service or step that started it)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.seen = {}  # (pid, ip, port) -> record
        self.errors = []

    def watch(self, pid: int, label: str):
        with self._lock:
            self._roots[pid] = label

    def unwatch(self, pid: int):
        self.poll()  # one last look before the process tree is gone
        with self._lock:
            self._roots.pop(pid, None)

    def poll(self):
        with self._lock:
            roots = dict(self._roots)
        if not roots:
            return
        try:
            table = self._table()
            for root, label in roots.items():
                tree = descendants([root], table)
                for pid, ip, port, state in external(self._conns(tree), self.allow):
                    key = (pid, ip, port)
                    if key not in self.seen:
                        self.seen[key] = {"pid": pid, "process": table.get(pid, (0, "?"))[1], "remote": f"{ip}:{port}",
                                          "state": state, "during": label}
        except Exception as exc:  # a broken poll must not pass silently
            if len(self.errors) < 5:
                self.errors.append(f"{type(exc).__name__}: {exc}")

    def _loop(self):
        while not self._stop.wait(self.interval_s):
            self.poll()

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> list:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        self.poll()
        return list(self.seen.values())


if __name__ == "__main__":
    # Diagnostic: python -I egress.py <pid> lists that process tree's external connections now.
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else os.getpid()
    print(external(connections(descendants([pid], process_table())), []))
