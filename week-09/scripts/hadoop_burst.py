#!/usr/bin/env python3
"""Prepare identical FM inputs or submit/observe a bounded Hadoop burst.

No SSH credentials or hostnames are embedded. Raw manifests stay in runtime/.
Submitting requires --execute; otherwise launch prints its plan only.
"""
import argparse
import datetime as dt
import getpass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
TRANSPORT = None
SSH_KEY = None
REMOTE_ROOT = None
HADOOP_HOME = None
sys.path.insert(0, str(ROOT / 'week-07/scripts'))
from event_generator import generate_events
from streaming import FlajoletMartin


def ssh_prefix():
    prefix = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5']
    if SSH_KEY:
        prefix += ['-i', SSH_KEY]
    return prefix


def execution(command):
    if TRANSPORT:
        return ssh_prefix() + [TRANSPORT, 'source /etc/profile.d/hadoop.sh; exec ' + shlex.join(command)]
    return command


def run(command):
    return subprocess.run(execution(command), text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True, timeout=60).stdout


def exists(path):
    return subprocess.run(execution(['hdfs', 'dfs', '-test', '-e', path]),
                          timeout=30).returncode == 0


def identity():
    return run(['id', '-un']).strip() if TRANSPORT else getpass.getuser()


def owned_path(path, user):
    prefix = '/user/' + user + '/'
    if not path.startswith(prefix) or '..' in path.split('/'):
        raise ValueError('path must be inside the submitting user HDFS home')
    return path.rstrip('/')


def canonical_registers(text):
    result = {}
    for line in text.splitlines():
        key, value = line.split('\t')
        key, value = int(key), int(value)
        if key in result:
            raise ValueError('duplicate register in reducer output')
        result[key] = value
    return result


def checksum(registers):
    content = ''.join(f'{k}\t{v}\n' for k, v in sorted(registers.items()))
    return hashlib.sha256(content.encode()).hexdigest()


def start_epoch(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('start time must include UTC offset or Z')
    return parsed.timestamp()


def api(base, endpoint):
    url = base.rstrip('/') + '/ws/v1/cluster/' + endpoint
    if TRANSPORT:
        code = ('import urllib.request; print(urllib.request.urlopen('
                + repr(url) + ',timeout=10).read().decode())')
        return json.loads(run(['python3', '-c', code]))
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def health(base, hosts):
    metrics = api(base, 'metrics')['clusterMetrics']
    if metrics['activeNodes'] != 3 or metrics['unhealthyNodes'] or metrics['lostNodes']:
        raise RuntimeError('expected three healthy workers')
    for host in hosts:
        output = subprocess.run(ssh_prefix() + [host, 'cat /proc/meminfo; df -P / /home /data'],
                                text=True, capture_output=True, check=True, timeout=15).stdout
        available = re.search(r'^MemAvailable:\s+(\d+)', output, re.M)
        if not available or int(available[1]) < 2 * 1024 * 1024:
            raise RuntimeError('VM available RAM below 2 GiB, or unavailable')
        for percent in re.findall(r'\s(\d+)%\s/', output):
            if int(percent) > 85:
                raise RuntimeError('filesystem usage above 85%')
        swap_total = re.search(r'^SwapTotal:\s+(\d+)', output, re.M)
        swap_free = re.search(r'^SwapFree:\s+(\d+)', output, re.M)
        if swap_total and swap_free and int(swap_total[1]) > int(swap_free[1]):
            raise RuntimeError('swap is in use; review health before experiment')
    return metrics


def prepare(args):
    user = identity()
    target = owned_path(args.hdfs_input, user)
    if exists(target):
        raise RuntimeError('input already exists; refusing to replace it')
    args.evidence.mkdir(parents=True, exist_ok=False)
    sketch = FlajoletMartin(128)
    files = [(args.evidence / f'events-{i}.jsonl').open('w', encoding='utf-8', newline='\n')
             for i in range(3)]
    try:
        for i, event in enumerate(generate_events(10_000, 1000, 100, .03, 4099)):
            files[i % 3].write(json.dumps(event, sort_keys=True, separators=(',', ':')) + '\n')
            sketch.add(event['user_id'])
    finally:
        for handle in files:
            handle.close()
    baseline = dict(enumerate(sketch.registers))
    (args.evidence / 'expected-registers.json').write_text(json.dumps(baseline))
    manifest = dict(records=10_000, users=1000, pages=100, seed=4099,
                    registers=128, expected_sha256=checksum(baseline), files=[])
    for path in sorted(args.evidence.glob('events-*.jsonl')):
        manifest['files'].append(dict(name=path.name, bytes=path.stat().st_size,
                                     sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (args.evidence / 'input-manifest.json').write_text(json.dumps(manifest, indent=2))
    run(['hdfs', 'dfs', '-mkdir', '-p', target])
    local_files = sorted(args.evidence.glob('events-*.jsonl'))
    upload_files = list(map(str, local_files))
    if TRANSPORT:
        remote_input = REMOTE_ROOT + '/runtime/prepared-' + str(time.time_ns())
        run(['mkdir', '-p', remote_input])
        scp = ['scp', '-q', '-o', 'BatchMode=yes']
        if SSH_KEY:
            scp += ['-i', SSH_KEY]
        subprocess.run(scp + upload_files + [TRANSPORT + ':' + remote_input + '/'],
                       check=True, timeout=60)
        upload_files = [remote_input + '/' + path.name for path in local_files]
    run(['hdfs', 'dfs', '-put', *upload_files, target])
    print(json.dumps(manifest, indent=2))


def command_for(input_path, output, name, user):
    source = (PurePosixPath(REMOTE_ROOT) if REMOTE_ROOT else ROOT) / 'week-07/scripts'
    if TRANSPORT:
        jars = run(['find', HADOOP_HOME + '/share/hadoop/tools/lib', '-maxdepth', '1',
                    '-name', 'hadoop-streaming-*.jar']).splitlines()
    else:
        jars = sorted((Path(HADOOP_HOME) / 'share/hadoop/tools/lib').glob('hadoop-streaming-*.jar'))
    if len(jars) != 1:
        raise RuntimeError('expected one Hadoop Streaming jar')
    properties = {
        'mapreduce.job.name': name,
        'mapreduce.job.reduces': 1,
        'mapreduce.map.speculative': 'false',
        'mapreduce.reduce.speculative': 'false',
        'yarn.app.mapreduce.am.staging-dir': '/user/' + user + '/.staging',
        'yarn.app.mapreduce.am.resource.mb': 1024,
        'yarn.app.mapreduce.am.command-opts': '-Xmx512m',
        'mapreduce.map.memory.mb': 1024,
        'mapreduce.reduce.memory.mb': 1024,
        'mapreduce.map.java.opts': '-Xmx512m',
        'mapreduce.reduce.java.opts': '-Xmx512m',
        'mapreduce.map.maxattempts': 1,
        'mapreduce.reduce.maxattempts': 1,
    }
    command = ['hadoop', 'jar', str(jars[0])]
    for key, value in properties.items():
        command += ['-D', f'{key}={value}']
    command += ['-files', ','.join(str(source / p) for p in
                                  ('hadoop/fm_mapper.py', 'hadoop/fm_reducer.py', 'streaming.py')),
                '-mapper', 'python3 fm_mapper.py 128', '-reducer', 'python3 fm_reducer.py',
                '-input', input_path, '-output', output]
    return command


def launch(args):
    user = identity()
    input_path = owned_path(args.hdfs_input, user)
    output_root = owned_path(args.hdfs_output, user)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.stage):
        raise ValueError('stage must contain only letters, digits, underscores or hyphens')
    before_clock = time.time()
    remote_clock = float(run(['python3', '-c', 'import time; print(time.time())'])) if TRANSPORT else before_clock
    after_clock = time.time()
    offset = remote_clock - (before_clock + after_clock) / 2 if TRANSPORT else 0
    def clock():
        return time.time() + offset
    target = start_epoch(args.start_at) if args.start_at else clock()
    expected = {int(k): v for k, v in json.loads(args.expected.read_text()).items()}
    if set(expected) != set(range(128)):
        raise ValueError('expected all 128 registers')
    rows = [dict(index=i, name=f'week09-{args.stage}-{user}-{i}',
                 output=f'{output_root}/{args.stage}/job-{i}') for i in range(args.jobs)]
    for row in rows:
        row['command'] = command_for(input_path, row['output'], row['name'], user)
    if not args.execute:
        print(json.dumps(dict(dry_run=True, scheduled_epoch=target, jobs=rows), indent=2))
        return 0
    hosts = [host for host in args.hosts.split(',') if host]
    if len(hosts) != 4:
        raise ValueError('--hosts must list controller and all three workers for health checks')
    health(args.rm_url, hosts)
    if args.start_at and target < clock():
        raise ValueError('scheduled start already passed during preflight; choose a later time')
    run(['hdfs', 'dfs', '-test', '-r', input_path])
    for row in rows:
        if exists(row['output']):
            raise RuntimeError('output already exists')
    args.evidence.mkdir(parents=True, exist_ok=False)
    manifest = dict(stage=args.stage, user=user, scheduled_epoch=target,
                    controller_clock_offset_seconds=offset,
                    clock_sample_uncertainty_seconds=(after_clock - before_clock) / 2,
                    poll_seconds=2, expected_sha256=checksum(expected), jobs=rows,
                    queue_time_note='observed RUNNING means application manager running, not first task')
    processes, readers = [], []
    abort_reason = None
    seen_ids = set()
    snapshots = (args.evidence / 'observations.jsonl').open('w')

    def read_log(process, row):
        with (args.evidence / f'job-{row["index"]}.log').open('w') as log:
            for line in process.stdout:
                log.write(line)
                log.flush()
                match = re.search(r'application_\d+_\d+', line)
                if match:
                    row['application_id'] = match[0]

    def save():
        path = args.evidence / 'manifest.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(manifest, indent=2))
        temporary.replace(path)

    try:
        while clock() < target:
            time.sleep(max(0, min(.1, target - clock())))
        for row in rows:
            row['submitted_epoch'] = clock()
            process = subprocess.Popen(execution(row['command']), stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True)
            processes.append(process)
            reader = threading.Thread(target=read_log, args=(process, row), daemon=True)
            reader.start()
            readers.append(reader)
        last_health = 0
        while True:
            now = clock()
            if now - target > args.timeout:
                raise RuntimeError('stage timeout')
            if now - last_health >= 15:
                metrics = health(args.rm_url, hosts)
                snapshots.write(json.dumps(dict(time=now, metrics=metrics)) + '\n')
                last_health = now
            apps = api(args.rm_url, 'apps').get('apps') or {}
            for app in apps.get('app', []):
                for row in rows:
                    # Exact unique name and owner also discover IDs if the client
                    # has not printed one yet. Never cancel an unrelated app.
                    if app.get('name') == row['name'] and app.get('user') == user:
                        seen_ids.add(app['id'])
                        row['application_id'] = app['id']
                        row['state'] = app['state']
                        row['final_status'] = app['finalStatus']
                        row['rm_started_ms'] = app.get('startedTime')
                        row['rm_finished_ms'] = app.get('finishedTime')
                        if app['state'] == 'RUNNING' and 'first_observed_running_epoch' not in row:
                            row['first_observed_running_epoch'] = now
                        snapshots.write(json.dumps(dict(time=now, app=app)) + '\n')
            snapshots.flush()
            for process, row in zip(processes, rows):
                if process.poll() is not None and 'client_finished_epoch' not in row:
                    row.update(client_finished_epoch=now, returncode=process.returncode)
            save()
            if all(process.poll() is not None for process in processes):
                break
            if any(process.poll() not in (None, 0) for process in processes):
                raise RuntimeError('a submission/job client failed')
            time.sleep(2)
    except (Exception, KeyboardInterrupt) as exc:
        abort_reason = str(exc) or 'interrupted'
        manifest['abort_reason'] = abort_reason
        # IDs came from exact name+owner REST matches or each owned client log.
        seen_ids.update(row['application_id'] for row in rows if 'application_id' in row)
        for app_id in sorted(seen_ids):
            subprocess.run(execution(['yarn', 'application', '-kill', app_id]), timeout=30)
        for process in processes:
            if process.poll() is None:
                process.terminate()
    finally:
        for process in processes:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for reader in readers:
            reader.join(timeout=5)
        snapshots.close()
        save()
    if not abort_reason:
        for row in rows:
            if row.get('returncode') != 0:
                continue
            if 'application_id' in row:
                final_app = api(args.rm_url, 'apps/' + row['application_id'])['app']
                row.update(state=final_app['state'], final_status=final_app['finalStatus'],
                           rm_finished_ms=final_app.get('finishedTime'))
            result = run(['hdfs', 'dfs', '-cat', row['output'] + '/part-*'])
            (args.evidence / f'job-{row["index"]}-registers.tsv').write_text(result)
            registers = canonical_registers(result)
            row['registers_match'] = registers == expected
            row['output_sha256'] = checksum(registers)
            row['turnaround_seconds'] = row['client_finished_epoch'] - row['submitted_epoch']
            if 'first_observed_running_epoch' in row:
                row['observed_am_wait_seconds'] = row['first_observed_running_epoch'] - row['submitted_epoch']
        manifest['postflight'] = health(args.rm_url, hosts)
    save()
    good = not abort_reason and all(r.get('registers_match') and r.get('returncode') == 0 for r in rows)
    print(json.dumps(dict(success=good, manifest=str(args.evidence / 'manifest.json'))))
    return 0 if good else 1


def main():
    global TRANSPORT, SSH_KEY, REMOTE_ROOT, HADOOP_HOME
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--hdfs-input', required=True)
    prep.add_argument('--evidence', type=Path, required=True)
    batch = sub.add_parser('launch')
    for flag in ('hdfs-input', 'hdfs-output', 'stage', 'rm-url'):
        batch.add_argument('--' + flag, required=True)
    batch.add_argument('--jobs', type=int, choices=range(1, 16), default=1)
    batch.add_argument('--expected', type=Path, required=True)
    batch.add_argument('--evidence', type=Path, required=True)
    batch.add_argument('--hosts', default=os.environ.get('HADOOP_HOSTS', ''))
    batch.add_argument('--start-at', help='ISO timestamp with offset; both users choose same time')
    batch.add_argument('--timeout', type=int, default=1200)
    batch.add_argument('--execute', action='store_true')
    for part in (prep, batch):
        part.add_argument('--gateway', help='optional user@controller; run from your workstation')
        part.add_argument('--ssh-key', help='local SSH key path, never uploaded')
        part.add_argument('--remote-root', help='absolute POSIX checkout path on controller')
        part.add_argument('--hadoop-home', default=os.environ.get('HADOOP_HOME', '/opt/hadoop'))
    args = parser.parse_args()
    if args.gateway and (not args.remote_root or not args.remote_root.startswith('/')):
        parser.error('--gateway requires an absolute --remote-root')
    TRANSPORT, SSH_KEY, REMOTE_ROOT = args.gateway, args.ssh_key, args.remote_root
    HADOOP_HOME = args.hadoop_home
    if args.action == 'launch' and not 1 <= args.timeout <= 1200:
        parser.error('timeout must be 1–1200 seconds')
    return prepare(args) if args.action == 'prepare' else launch(args)


if __name__ == '__main__':
    raise SystemExit(main())
