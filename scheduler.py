"""FCFS, non-preemptive SJF, and Round Robin on a single simulated CPU."""
from collections import deque
from statistics import mean


def compare(workload, quantum):
    if type(quantum) is not int or not 1 <= quantum <= 1000:
        raise ValueError("Quantum must be a whole number from 1 to 1000.")
    if not isinstance(workload, list) or not 1 <= len(workload) <= 12:
        raise ValueError("Enter 1 to 12 processes.")
    arrivals, bursts = [], []
    for job in workload:
        if not isinstance(job, dict):
            raise ValueError("Each process needs an arrival and burst.")
        arrival, burst = job.get("arrival"), job.get("burst")
        if type(arrival) is not int or type(burst) is not int or not 0 <= arrival <= 1000 or not 1 <= burst <= 100:
            raise ValueError("Arrival must be 0–1000 and burst must be 1–100, using whole numbers.")
        arrivals.append(arrival)
        bursts.append(burst)
    return [simulate(policy, arrivals, bursts, quantum) for policy in ("FCFS", "SJF", "Round Robin")]


def simulate(policy, arrivals, bursts, quantum):
    upcoming = deque(sorted(range(len(arrivals)), key=arrivals.__getitem__))
    ready = deque()
    remaining = bursts.copy()
    first_start, finish = {}, {}
    timeline = []
    clock = 0

    def admit():
        while upcoming and arrivals[upcoming[0]] <= clock:
            ready.append(upcoming.popleft())

    while upcoming or ready:
        admit()
        if not ready:
            next_time = arrivals[upcoming[0]]
            timeline.append({"job": "Idle", "start": clock, "end": next_time})
            clock = next_time
            admit()
        if policy == "SJF":
            job = min(ready, key=lambda index: (bursts[index], arrivals[index], index))
            ready.remove(job)
        else:
            job = ready.popleft()
        first_start.setdefault(job, clock)
        duration = min(remaining[job], quantum) if policy == "Round Robin" else remaining[job]
        timeline.append({"job": f"P{job + 1}", "start": clock, "end": clock + duration})
        clock += duration
        remaining[job] -= duration
        admit()
        if remaining[job]:
            ready.append(job)
        else:
            finish[job] = clock

    rows = []
    for job, arrival in enumerate(arrivals):
        turnaround = finish[job] - arrival
        rows.append({"job": f"P{job + 1}", "completion": finish[job], "turnaround": turnaround,
                     "waiting": turnaround - bursts[job], "response": first_start[job] - arrival})
    return {"policy": policy, "timeline": timeline, "rows": rows,
            "averages": {key: round(mean(row[key] for row in rows), 2)
                         for key in ("waiting", "turnaround", "response")}}
