"""Measure local Linux activity and evaluate transparent rules."""
from collections import deque
from datetime import datetime
from pathlib import Path
from statistics import mean
from threading import Lock
from time import monotonic

import psutil

MIB = 1024 ** 2
WINDOW = 15
INTERVAL = 2


def vm_counters():
    try:
        with Path("/proc/vmstat").open() as stream:
            return {key: int(value) for key, value in map(str.split, stream)}
    except (OSError, ValueError):
        return {}


def delta_rate(previous, current, elapsed):
    if previous is None or current is None or current < previous:
        return None
    return (current - previous) / elapsed


class Monitor:
    def __init__(self):
        self.history = deque(maxlen=60)
        self.lock = Lock()
        self.previous = None
        psutil.cpu_percent()

    def sample(self):
        timestamp = monotonic()
        vm = vm_counters()
        disk = psutil.disk_io_counters()
        memory = psutil.virtual_memory()
        rows = []
        processes = {}
        old_time, old_vm, old_disk, old_processes = self.previous or (timestamp, {}, None, {})
        elapsed = timestamp - old_time
        pids = psutil.pids()
        for pid in pids:
            try:
                p = psutil.Process(pid)
                with p.oneshot():
                    key = (pid, p.create_time())
                    times = p.cpu_times()
                    total = times.user + times.system
                    rss = p.memory_info().rss
                    name = p.name()
            except psutil.Error:
                continue
            processes[key] = total
            cpu = delta_rate(old_processes.get(key), total, elapsed) if elapsed > 0 else None
            rows.append({"pid": pid, "name": name, "cpu": None if cpu is None else round(cpu * 100, 1),
                         "rss": round(rss / MIB, 1)})
        self.previous = (timestamp, vm, disk, processes)
        cpu = psutil.cpu_percent()
        if elapsed <= 0:
            return

        total_faults = delta_rate(old_vm.get("pgfault"), vm.get("pgfault"), elapsed)
        major = delta_rate(old_vm.get("pgmajfault"), vm.get("pgmajfault"), elapsed)
        swap_in = delta_rate(old_vm.get("pswpin"), vm.get("pswpin"), elapsed)
        swap_out = delta_rate(old_vm.get("pswpout"), vm.get("pswpout"), elapsed)
        storage = psutil.disk_usage("/")
        sample = {
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "cpu": cpu, "ram": memory.percent, "available_pct": memory.available / memory.total * 100,
            "available_mib": round(memory.available / MIB), "disk": storage.percent,
            "free_gib": round(storage.free / 1024 ** 3, 2), "processes": len(pids),
            "major": major, "minor": None if major is None or total_faults is None
            else max(0, total_faults - major),
            "swap": None if swap_in is None or swap_out is None else swap_in + swap_out,
            "read": delta_rate(getattr(old_disk, "read_bytes", None), getattr(disk, "read_bytes", None), elapsed),
            "write": delta_rate(getattr(old_disk, "write_bytes", None), getattr(disk, "write_bytes", None), elapsed),
            "elapsed": elapsed,
        }
        with self.lock:
            self.history.append((sample, rows))

    def report(self):
        with self.lock:
            frames = list(self.history)
        if not frames:
            return {"history": [], "recommendations": [], "top": []}
        window = frames[-WINDOW:]
        latest, rows = frames[-1]
        return {
            "history": [sample for sample, _ in frames],
            "recommendations": recommendations(window),
            "top": sorted(rows, key=lambda row: (row["cpu"] or 0, row["rss"]), reverse=True)[:10],
            "window_samples": len(window),
            "window_seconds": round(sum(sample["elapsed"] for sample, _ in window)),
            "ready": len(window) == WINDOW,
        }


def recommendations(window):
    samples = [sample for sample, _ in window]
    last = samples[-1]
    items = []
    if last["disk"] >= 90:
        items.append({
            "title": "Free space on the root filesystem",
            "evidence": f"/ is {last['disk']:.1f}% used, with {last['free_gib']:.2f} GiB free.",
            "action": "Review large downloads, logs, and temporary files. Verify available space afterward.",
        })
    if len(samples) < WINDOW:
        return items
    duration = round(sum(sample["elapsed"] for sample in samples))
    cpu_average = mean(sample["cpu"] for sample in samples)
    high_cpu = sum(sample["cpu"] >= 85 for sample in samples)
    if high_cpu >= 12:
        cpu_by_process = {}
        for sample, rows in window:
            for row in rows:
                if row["cpu"] is not None:
                    key = (row["pid"], row["name"])
                    cpu_by_process[key] = cpu_by_process.get(key, 0) + row["cpu"] * sample["elapsed"]
        leader = ""
        if cpu_by_process:
            (pid, name), cpu_seconds_percent = max(cpu_by_process.items(), key=lambda item: item[1])
            average = cpu_seconds_percent / sum(s["elapsed"] for s in samples)
            leader = f" Top observed process: {name} (PID {pid}), {average:.1f}% of one logical CPU on average."
        items.append({
            "title": "Review sustained CPU load",
            "evidence": f"CPU averaged {cpu_average:.1f}% over {duration}s and reached 85% in {high_cpu}/{WINDOW} samples.{leader}",
            "action": "Review the busiest process. If the work can wait, pause it in its application and compare the next window.",
        })

    low_memory = sum(sample["available_pct"] <= 10 for sample in samples)
    paging = [sample for sample in samples if sample["swap"] is not None and sample["swap"] > 0
              and sample["major"] is not None and sample["major"] > 0 and sample["available_pct"] <= 10]
    if low_memory >= 12:
        biggest = max(window[-1][1], key=lambda row: row["rss"], default=None)
        consumer = f" Largest observed resident footprint: {biggest['name']} ({biggest['rss']:.1f} MiB RSS)." if biggest else ""
        evidence = f"Available RAM was at or below 10% in {low_memory}/{WINDOW} samples. Latest available RAM: {last['available_mib']} MiB."
        if len(paging) >= 3:
            evidence += (f" {len(paging)} samples showed both swap activity and major faults during low RAM "
                         f"(averages in those samples: {mean(s['swap'] for s in paging):.1f} swap pages/s, "
                         f"{mean(s['major'] for s in paging):.1f} major faults/s).")
        items.append({
            "title": "Investigate memory pressure" if len(paging) >= 3 else "Review low available memory",
            "evidence": evidence + consumer,
            "action": "Save your work, close unused applications, and compare available RAM and paging in the next window.",
        })
    return items
