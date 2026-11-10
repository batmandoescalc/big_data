#!/usr/bin/env python3
"""Run sequential capped probes on one Linux worker; raw evidence stays local."""
import argparse
import getpass
import json
from pathlib import Path
import subprocess
import sys
import threading
import time


def host_memory():
    fields = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        fields[key] = int(value.split()[0]) * 1024
    if fields['MemAvailable'] < 2 * 1024**3:
        raise RuntimeError('VM available memory below 2 GiB')
    if fields['SwapTotal'] != fields['SwapFree']:
        raise RuntimeError('swap is in use; stop and review host health')
    return {key: fields[key] for key in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    cases = [('exact-set', cap, 12_000_000) for cap in (128, 256, 512)]
    cases += [('fm', 128, count) for count in (250_000, 1_000_000)]
    if not args.execute:
        print(json.dumps(dict(dry_run=True, cases=cases)))
        return 0
    initial = host_memory()
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(before=initial, cases=[])
    study = str(time.time_ns())
    for index, (mode, cap, records) in enumerate(cases):
        before = host_memory()
        unit = f'cse4099-memory-{study}-{index}'
        command = ['sudo', '-n', 'systemd-run', '--unit=' + unit, '--wait', '--pipe',
                   '-p', 'User=' + getpass.getuser(), '-p', f'MemoryMax={cap}M',
                   '-p', 'MemorySwapMax=0', '-p', 'OOMPolicy=kill', '-p', 'TasksMax=32',
                   '-p', 'RuntimeMaxSec=120', '-p', 'CPUQuota=100%',
                   sys.executable, str(Path(__file__).with_name('memory_probe.py')),
                   '--mode', mode, '--expected-cap-mib', str(cap), '--records', str(records)]
        samples = []
        with (args.output / f'{index}-{mode}-{cap}.log').open('w') as log:
            process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True)
            def drain():
                for line in process.stdout:
                    log.write(line)
                    log.flush()
            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            try:
                started = time.monotonic()
                while process.poll() is None:
                    samples.append(dict(elapsed=time.monotonic() - started, **host_memory()))
                    if time.monotonic() - started > 135:
                        raise RuntimeError('supervisor timeout')
                    time.sleep(.25)
            except BaseException:
                subprocess.run(['sudo', '-n', 'systemctl', 'stop', unit + '.service'], timeout=15)
                process.wait(timeout=15)
                raise
            finally:
                reader.join(timeout=5)
        detail = subprocess.run(['sudo', '-n', 'systemctl', 'show', unit + '.service',
                                 '-p', 'LoadState', '-p', 'Result', '-p', 'ExecMainCode',
                                 '-p', 'ExecMainStatus', '-p', 'MemoryPeak', '-p', 'MemoryMax',
                                 '-p', 'MemorySwapMax'], text=True, capture_output=True, timeout=10).stdout
        case = dict(mode=mode, cap_mib=cap, requested_records=records,
                    command=command, supervisor_returncode=process.returncode,
                    service_properties=detail, host_before=before, host_after=host_memory(),
                    host_samples=samples)
        report['cases'].append(case)
        (args.output / 'study.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(dict(case=index, mode=mode, cap_mib=cap,
                              returncode=process.returncode)), flush=True)
        # Exact state is expected to reach the cap. A bounded sketch must finish.
        log_text = (args.output / f'{index}-{mode}-{cap}.log').read_text()
        if '"kind": "start"' not in log_text:
            raise RuntimeError('probe never verified its cap; stop study')
        if mode == 'fm' and process.returncode != 0:
            raise RuntimeError('bounded sketch failed; inspect evidence')
        if mode == 'exact-set' and process.returncode != 0 and not (
                'Result=oom-kill' in detail or '"kind": "memory_error"' in log_text):
            raise RuntimeError('exact failure was not confirmed memory exhaustion')
        time.sleep(2)
    report['after'] = host_memory()
    (args.output / 'study.json').write_text(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
