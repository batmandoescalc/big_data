#!/usr/bin/env python3
"""Extract a public, account-free summary from private capped-process evidence."""
import argparse
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads((args.study / 'study.json').read_text())
    summary = dict(python='3.9.25', platform='Linux, cgroup v2',
                   key_bytes=32, input='unique ASCII hexadecimal keys, generated and discarded',
                   units='MiB = 2^20 bytes; GB = 10^9 bytes', cases=[])
    ratios = []
    points = []
    for index, case in enumerate(raw['cases']):
        text = (args.study / f'{index}-{case["mode"]}-{case["cap_mib"]}.log').read_text()
        records = [json.loads(line) for line in text.splitlines() if line.startswith('{')]
        last = records[-1]
        oom = 'Result=oom-kill' in case['service_properties']
        row = dict(mode=case['mode'], cap_mib=case['cap_mib'],
                   outcome='cgroup-oom-kill' if oom else last['kind'],
                   last_logged_records=last['records'],
                   last_logged_peak_rss_mib=last['peak_rss_kib'] / 1024,
                   last_logged_cgroup_peak_mib=last['memory_peak_bytes'] / 1024**2,
                   elapsed_to_last_log_seconds=last['elapsed_seconds'])
        if oom:
            row['next_checkpoint_records'] = last['records'] + 25_000
            row['input_payload_gb_at_last_checkpoint'] = last['input_payload_bytes'] / 1e9
            row['cgroup_peak_mib_at_failure'] = case['cap_mib']
            ratios.append(case['cap_mib'] * 1024**2 / last['records'])
        else:
            row['logical_state_bytes'] = last['logical_state_bytes']
            row['registers'] = last['registers']
        summary['cases'].append(row)
        for record in records:
            if record['kind'] == 'checkpoint':
                points.append(dict(mode=case['mode'], cap_mib=case['cap_mib'],
                                   records=record['records'],
                                   cgroup_mib=record['memory_current_bytes'] / 1024**2,
                                   peak_rss_mib=record['peak_rss_kib'] / 1024))
    samples = [sample['MemAvailable'] for c in raw['cases'] for sample in c['host_samples']]
    summary['host_min_available_mib'] = min(samples) / 1024**2
    summary['swap_used_bytes'] = max(s['SwapTotal'] - s['SwapFree']
                                     for c in raw['cases'] for s in c['host_samples'])
    usable = raw['before']['MemAvailable'] - 2 * 1024**3
    summary['planning_estimate'] = dict(
        before_available_mib=raw['before']['MemAvailable'] / 1024**2,
        reserved_headroom_mib=2048, usable_for_model_bytes=usable,
        observed_effective_bytes_per_key_range=[min(ratios), max(ratios)],
        estimated_keys_range=[int(usable / max(ratios)), int(usable / min(ratios))],
        estimated_unique_key_payload_gb_range=[usable / max(ratios) * 32 / 1e9,
                                               usable / min(ratios) * 32 / 1e9],
        limitation='Illustrative extrapolation with 2 GiB reserve, not an observed VM crash. '
                   'Set resize peaks, allocator behavior, keys and other workloads change the threshold.')
    available = raw['before']['MemAvailable']
    summary['planning_estimate']['unreserved_available_ram_keys_range'] = [
        int(available / max(ratios)), int(available / min(ratios))]
    summary['planning_estimate']['unreserved_unique_key_payload_gb_range'] = [
        available / max(ratios) * 32 / 1e9, available / min(ratios) * 32 / 1e9]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    points_path = args.output.with_name(args.output.stem + '-points.csv')
    with points_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['mode', 'cap_mib', 'records',
                                                    'cgroup_mib', 'peak_rss_mib'])
        writer.writeheader()
        writer.writerows(points)
    summary['memory_points_csv'] = points_path.name
    args.output.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'memory_points'}, indent=2))


if __name__ == '__main__':
    main()
