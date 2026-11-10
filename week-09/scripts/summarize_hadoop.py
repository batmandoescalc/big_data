#!/usr/bin/env python3
"""Summarize private stage manifests without usernames, hosts or HDFS paths."""
import argparse
import json
from pathlib import Path
import re
import statistics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stages', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = dict(accounts=1, records_per_job=10_000, registers=128,
                  note='Same-account applications; not a multi-user scheduling experiment. '
                       'Single stage per count; polling/SSH overhead affects observed times.', stages=[])
    for folder in args.stages:
        manifest = json.loads((folder / 'manifest.json').read_text())
        rows = []
        ids = {r['application_id'] for r in manifest['jobs']}
        states = {}
        max_running = max_accepted = 0
        observations = [json.loads(line) for line in (folder / 'observations.jsonl').read_text().splitlines()]
        for observation in observations:
            app = observation.get('app', {})
            if app.get('id') in ids:
                states[app['id']] = app['state']
                max_running = max(max_running, sum(v == 'RUNNING' for v in states.values()))
                max_accepted = max(max_accepted, sum(v == 'ACCEPTED' for v in states.values()))
        for row in manifest['jobs']:
            log = (folder / f'job-{row["index"]}.log').read_text()
            counters = {}
            for label in ('Map input records', 'Map output records', 'Reduce output records',
                          'Launched map tasks', 'Launched reduce tasks'):
                match = re.search(re.escape(label) + r'=(\d+)', log)
                if match:
                    counters[label] = int(match[1])
            rows.append(dict(application_id=row['application_id'],
                             client_turnaround_seconds=row.get('turnaround_seconds'),
                             observed_am_wait_seconds=row.get('observed_am_wait_seconds'),
                             final_status=row.get('final_status'),
                             registers_match=row.get('registers_match'),
                             output_sha256=row.get('output_sha256'), counters=counters))
        submissions = [row['submitted_epoch'] for row in manifest['jobs']]
        finishes = [row['client_finished_epoch'] for row in manifest['jobs']]
        report['stages'].append(dict(
            jobs=len(rows), submitted_spread_seconds=max(submissions) - min(submissions),
            total_stage_seconds=max(finishes) - min(submissions),
            median_client_turnaround_seconds=statistics.median(r['client_turnaround_seconds'] for r in rows),
            max_observed_running=max_running, max_observed_accepted=max_accepted,
            successful_outputs=sum(r['registers_match'] is True for r in rows), applications=rows))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
