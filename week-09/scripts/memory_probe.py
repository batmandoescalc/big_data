#!/usr/bin/env python3
"""Measure retained state, only inside a verified cgroup v2 memory cap."""
import argparse
import json
from pathlib import Path
import resource
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'week-07/scripts'))
from streaming import FlajoletMartin


def cgroup_path():
    for line in Path('/proc/self/cgroup').read_text().splitlines():
        if line.startswith('0::'):
            return Path('/sys/fs/cgroup') / line[3:].lstrip('/')
    raise RuntimeError('cgroup v2 required')


def validate_limits(folder, expected_mib):
    maximum = (folder / 'memory.max').read_text().strip()
    swap = (folder / 'memory.swap.max').read_text().strip()
    if maximum != str(expected_mib * 1024 * 1024) or swap != '0':
        raise RuntimeError('refusing allocation: memory/swap cap does not match request')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('exact-set', 'fm'), required=True)
    parser.add_argument('--expected-cap-mib', type=int, choices=(128, 256, 512), required=True)
    parser.add_argument('--records', type=int, default=12_000_000)
    parser.add_argument('--checkpoint', type=int, default=25_000)
    parser.add_argument('--registers', type=int, default=16)
    args = parser.parse_args()
    if min(args.records, args.checkpoint, args.registers) <= 0:
        parser.error('records, checkpoint and registers must be positive')
    folder = cgroup_path()
    validate_limits(folder, args.expected_cap_mib)
    started = time.monotonic()
    state = set() if args.mode == 'exact-set' else FlajoletMartin(args.registers)

    def emit(kind, count):
        fields = dict(kind=kind, mode=args.mode, records=count, distinct_input=count,
                      input_payload_bytes=count * 32, key_bytes=32,
                      elapsed_seconds=time.monotonic() - started,
                      peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      memory_current_bytes=int((folder / 'memory.current').read_text()),
                      memory_peak_bytes=int((folder / 'memory.peak').read_text()),
                      cap_mib=args.expected_cap_mib, swap_max_bytes=0,
                      python=sys.version.split()[0])
        if args.mode == 'exact-set':
            fields.update(retained_keys=len(state), table_bytes=sys.getsizeof(state))
        else:
            fields.update(registers=args.registers, logical_state_bytes=state.memory_bytes)
            if kind == 'complete':
                fields['estimate'] = state.estimate()
        print(json.dumps(fields), flush=True)

    emit('start', 0)
    count = 0
    try:
        for index in range(args.records):
            key = format(index, '032x').encode('ascii')
            state.add(key)
            count = index + 1
            if count % args.checkpoint == 0:
                emit('checkpoint', count)
        emit('complete', count)
    except MemoryError:
        # Best effort; the cgroup OOM killer can terminate before Python catches it.
        emit('memory_error', count)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
