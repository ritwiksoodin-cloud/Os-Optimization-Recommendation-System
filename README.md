OS Optimization Recommendation System
=====================================

A dashboard for monitoring Linux resource usage and comparing CPU scheduling algorithms. The recommendation panel shows the measurements behind each finding.

Run the dashboard
-----------------

Use Python 3.10+ on Linux or in an Ubuntu WSL terminal on Windows. With WSL, measurements describe the Linux environment.

```bash
cd os_optimizer_light
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:8080**. Use `python app.py --port 8081` if port 8080 is busy. Stop the server with Ctrl+C. The server listens on localhost. If you open `web/index.html` directly, the page shows how to start the server.

Live monitoring
---------------

- The collector reads CPU, available memory, root filesystem usage, disk throughput, and visible processes using psutil. Linux `/proc/vmstat` supplies cumulative fault and swap counters. The app subtracts consecutive counter values and divides by elapsed seconds to produce rates.
- The dashboard keeps the latest 60 samples in memory. The target interval is two seconds, plus collection time. A dash indicates an unavailable measurement.
- Total CPU utilization is system-wide. The top process table reports usage relative to one logical CPU, so a multi-threaded process can exceed 100%. The process list depends on what the OS exposes to the current user.
- Root filesystem capacity and disk I/O throughput are distinct measurements. Containers may expose host-wide counters alongside container-scoped processes or storage.

| Rule | Trigger | Evidence shown |
| --- | --- | --- |
| Sustained CPU load | CPU at least 85% in 12 of the latest 15 samples | Window average, number of qualifying samples, and busiest observed process when available |
| Low available RAM | Available RAM at most 10% in 12 of 15 samples | Available RAM and the largest observed resident footprint |
| Memory pressure | Low-RAM rule plus at least three low-RAM samples with swap activity and major faults together | Swap and major fault rates across qualifying samples |
| Low root filesystem space | At least 90% used in the latest sample | Percent used and free GiB |

These thresholds are project defaults. Recommendations suggest actions and leave system changes to the operator. Page faults and disk activity are always shown when available. A fault count alone is insufficient to infer memory pressure.

Scheduling simulator
--------------------

Edit each process's arrival time and CPU burst and set a Round Robin quantum. The simulator runs FCFS, non-preemptive SJF, and Round Robin on the same workload on one simulated CPU. It records idle gaps and assumes zero context-switch overhead. Round Robin enqueues arrivals at a slice boundary before requeuing the process whose slice just ended.

- Turnaround = completion minus arrival.
- Waiting = turnaround minus burst.
- Response = first run minus arrival.

The result highlights the algorithms with the lowest measured average waiting and response times for that workload. The comparisons describe the simulation and do not change the Linux scheduler.

Capstone demo
-------------

1. Start the dashboard and wait about 30 seconds for a baseline.
2. Run a CPU-heavy task you can stop, such as a local video export. Watch it move up the process table and observe the CPU chart. Sustained system-wide usage must cross the rule threshold to produce a CPU recommendation.
3. Finish or pause the task and show the chart returning toward baseline and the recommendation clearing as the window rolls forward.
4. Run the scheduler with the prefilled workload. Expand each timeline and change the Round Robin quantum to show how the response and waiting times change.

The project keeps collection and rules in `monitor.py`, scheduling in `scheduler.py`, and the local server and browser frontend in `app.py` and `web/`.
