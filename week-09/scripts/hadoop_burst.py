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
# After its stdin closes, the remote batch gives job clients this long to exit
# on SIGTERM before it sends SIGKILL.
STOP_GRACE_SECONDS = 10
# YARN states in which an application is over and has nothing left to cancel.
TERMINAL_STATES = ('FINISHED', 'FAILED', 'KILLED')
# After an abort, list this stage's applications this many times, this far
# apart. A client can submit just before it is stopped, and the application
# then shows up in YARN a few seconds later.
CLEANUP_POLLS = 5
CLEANUP_POLL_SECONDS = 2
# Every VM must keep this much memory available (kB, as /proc/meminfo reports).
MIN_AVAILABLE_KB = 2 * 1024 * 1024
# Controller memory set aside for each job client before a stage may start.
# Measured in the 15-jobs-each round: about 209 MB per client JVM (15 clients
# used 3,137 MB). Rounded up to 256 MiB for headroom.
# shortcut: counts only this launcher's clients, not another account's that
# start at the same time; in a joint round both batches must fit together.
CLIENT_ALLOWANCE_KB = 256 * 1024
sys.path.insert(0, str(ROOT / 'week-07/scripts'))
from event_generator import generate_events
from streaming import FlajoletMartin


def ssh_prefix(stdin=False):
    # Concurrent Windows SSH clients must not compete for console stdin.
    # -n disconnects stdin; -T makes the no-terminal intent explicit.
    # Only the batch connection keeps stdin, and it is given a pipe.
    prefix = ['ssh'] + ([] if stdin else ['-n']) + [
        '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
        '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2']
    if SSH_KEY:
        prefix += ['-i', SSH_KEY]
    return prefix


def execution(command, stdin=False):
    if TRANSPORT:
        return ssh_prefix(stdin) + [TRANSPORT, 'source /etc/profile.d/hadoop.sh; exec ' + shlex.join(command)]
    return command


def run(command):
    return subprocess.run(execution(command), text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                          check=True, timeout=60).stdout


def exists(path):
    return subprocess.run(execution(['hdfs', 'dfs', '-test', '-e', path]),
                          stdin=subprocess.DEVNULL, timeout=30).returncode == 0


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


def stage_applications(base, names, user):
    """This stage's applications: exact job name and exact owner, nothing else.

    Every lookup and every cancel goes through this match, so the launcher
    cannot touch another user's application or an unrelated one.
    """
    apps = api(base, 'apps').get('apps') or {}
    return [app for app in apps.get('app', [])
            if app.get('name') in names and app.get('user') == user]


def stop_clients(processes):
    """Stop every job client and wait until each one is gone."""
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def cancel_stage_applications(base, names, user, known_ids):
    """Cancel every unfinished application of this stage; return (cancelled, failed).

    The list is read again several times because an application can appear
    after the abort. A cancel that fails or times out is retried on the next
    pass and never stops the other cancels.
    """
    pending, finished, cancelled = set(known_ids), set(), set()
    for attempt in range(CLEANUP_POLLS):
        if attempt:
            time.sleep(CLEANUP_POLL_SECONDS)
        try:
            for app in stage_applications(base, names, user):
                (finished if app.get('state') in TERMINAL_STATES else pending).add(app['id'])
        except Exception as exc:
            print(f'Cleanup could not list applications ({exc}); using known IDs.', flush=True)
        for app_id in sorted(pending - finished - cancelled):
            try:
                done = subprocess.run(execution(['yarn', 'application', '-kill', app_id]),
                                      stdin=subprocess.DEVNULL, timeout=30)
                if done.returncode == 0:
                    cancelled.add(app_id)
            except (subprocess.TimeoutExpired, OSError) as exc:
                print(f'Cancel of {app_id} did not finish ({exc}); will retry.', flush=True)
    return sorted(cancelled), sorted(pending - finished - cancelled)


def host_snapshot(host):
    command = ssh_prefix() + [host, 'cat /proc/meminfo; df -P / /home /data']
    for attempt in range(2):
        try:
            return subprocess.run(command, text=True, capture_output=True,
                                  stdin=subprocess.DEVNULL, check=True, timeout=20).stdout
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            if attempt:
                raise
            print('SSH health check delayed or failed; retrying once before aborting.', flush=True)


def clients_that_fit(available_kb):
    """How many job clients the controller can start and stay above the RAM guard."""
    return max(0, (available_kb - MIN_AVAILABLE_KB) // CLIENT_ALLOWANCE_KB)


def health_interval(rows):
    """Seconds between health checks: short until every job has reached YARN.

    The controller lost about 3 GB in 45 seconds while 30 clients started, so
    the launch window is when a 15-second gap is too long.
    """
    return 15 if all('application_id' in row for row in rows) else 5


def health(base, hosts, new_clients=0):
    """Raise unless the cluster is healthy; hosts lists the controller first.

    new_clients is the number of job clients about to start on the controller.
    """
    metrics = api(base, 'metrics')['clusterMetrics']
    if metrics['activeNodes'] != 3 or metrics['unhealthyNodes'] or metrics['lostNodes']:
        raise RuntimeError('expected three healthy workers')
    for index, host in enumerate(hosts):
        output = host_snapshot(host)
        found = re.search(r'^MemAvailable:\s+(\d+)', output, re.M)
        available = int(found[1]) if found else 0
        if available < MIN_AVAILABLE_KB:
            raise RuntimeError('VM available RAM below 2 GiB, or unavailable')
        if index == 0 and new_clients > clients_that_fit(available):
            raise RuntimeError(
                f'{new_clients} job clients need about {new_clients * CLIENT_ALLOWANCE_KB // 1024} MiB '
                f'on the controller, which has {available // 1024} MiB available; '
                f'only {clients_that_fit(available)} would fit above the 2 GiB guard')
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
                       stdin=subprocess.DEVNULL, check=True, timeout=60)
        upload_files = [remote_input + '/' + path.name for path in local_files]
    run(['hdfs', 'dfs', '-put', *upload_files, target])
    print(json.dumps(manifest, indent=2))


def batch_command(commands):
    """One command that starts every job client at once and stops them all together.

    A sign-in per job trips the SSH server's limit on simultaneous new
    connections at about ten jobs, so one connection carries the whole batch.
    Each client's lines come back tagged ``JOB<i> `` and its exit status as
    ``JOB<i> BURST_EXIT <code>``.

    Ending the local ssh does not stop the remote clients, so the script
    watches its own stdin. The launcher holds that stdin open. When it closes
    (launcher stopped or connection dropped), or on a signal, the script kills
    its whole process group: every client it started. ``setsid`` gives the
    script a process group of its own, so nothing else is in it.
    """
    # A signal makes the script signal its whole group once. `trap :` (handle,
    # not ignore) keeps the script itself alive to finish the steps below.
    lines = ["trap 'trap : TERM; kill -TERM 0' TERM HUP INT", 'pids=']
    for index, command in enumerate(commands):
        lines += ['{ ' + shlex.join(command) + ' 2>&1; echo "BURST_EXIT $?"; } | '
                  + f"sed -u 's/^/JOB{index} /' &",
                  'pids="$pids $!"']
    lines += [
        # Bash gives a background command an empty stdin unless it names one,
        # so only this watcher reads the launcher's pipe; <&0 is what names it.
        '{ cat >/dev/null; kill -TERM $$; } <&0 &',
        # Returns when every client has finished, or early on a signal.
        'wait $pids',
        # Stop whatever is left: clients after a signal, otherwise the watcher.
        'trap : TERM; kill -TERM 0',
        f'( sleep {STOP_GRACE_SECONDS}; kill -KILL 0 ) >/dev/null 2>&1 &',
        'wait $pids']
    return ['setsid', '-w', 'bash', '-c', '\n'.join(lines)]


class BatchClient:
    """One job's client inside the shared SSH connection."""

    def __init__(self, connection):
        self.connection = connection
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        # Closing stdin is the stop signal the remote script watches for.
        self.connection.stdin.close()

    def kill(self):
        self.connection.kill()

    def wait(self, timeout=None):
        self.connection.wait(timeout=timeout)
        return self.returncode


def route_batch_output(stream, clients, on_line, stray):
    """Send each tagged line to its job; a dropped connection fails the rest."""
    for line in stream:
        match = re.match(r'JOB(\d+) (.*)', line, re.S)
        if not match or int(match[1]) >= len(clients):
            stray(line)
            continue
        index, text = int(match[1]), match[2]
        finished = re.fullmatch(r'BURST_EXIT (\d+)\s*', text)
        if finished:
            clients[index].returncode = int(finished[1])
        else:
            on_line(index, text)
    for client in clients:
        if client.returncode is None:
            client.returncode = 255


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
    print('Checking cluster and VM health before submission...', flush=True)
    health(args.rm_url, hosts, len(rows))
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
    names = {row['name']: row for row in rows}
    snapshots = (args.evidence / 'observations.jsonl').open('w')

    def record(row, line, log):
        log.write(line)
        log.flush()
        match = re.search(r'application_\d+_\d+', line)
        if match:
            if 'application_id' not in row:
                print(f'Job {row["index"]}: submitted {match[0]}', flush=True)
            row['application_id'] = match[0]

    def read_log(process, row):
        with (args.evidence / f'job-{row["index"]}.log').open('w') as log:
            for line in process.stdout:
                record(row, line, log)

    def read_batch(connection, clients):
        logs = [(args.evidence / f'job-{row["index"]}.log').open('w') for row in rows]
        try:
            # Lines without a job tag (SSH banners and errors) are kept too.
            with (args.evidence / 'connection.log').open('w') as stray:
                route_batch_output(connection.stdout, clients,
                                   lambda index, line: record(rows[index], line, logs[index]),
                                   stray.write)
        finally:
            for log in logs:
                log.close()

    def save():
        path = args.evidence / 'manifest.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(manifest, indent=2))
        temporary.replace(path)

    try:
        print('Ready. Scheduled controller time: ' +
              dt.datetime.fromtimestamp(target, dt.timezone.utc).isoformat() +
              f'; jobs: {len(rows)}. Waiting for the start time...', flush=True)
        while clock() < target:
            time.sleep(max(0, min(.1, target - clock())))
        if TRANSPORT:
            # One SSH connection starts every client together. Its stdin stays
            # open for the whole stage; closing it stops the remote clients.
            started = clock()
            connection = subprocess.Popen(
                execution(batch_command([row['command'] for row in rows]), stdin=True),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, text=True)
            for row in rows:
                row['submitted_epoch'] = started
                processes.append(BatchClient(connection))
            reader = threading.Thread(target=read_batch, args=(connection, processes), daemon=True)
            reader.start()
            readers.append(reader)
        else:
            for row in rows:
                row['submitted_epoch'] = clock()
                process = subprocess.Popen(row['command'], stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True)
                processes.append(process)
                reader = threading.Thread(target=read_log, args=(process, row), daemon=True)
                reader.start()
                readers.append(reader)
        last_health = 0
        while True:
            now = clock()
            if now - target > args.timeout:
                raise RuntimeError('stage timeout')
            if now - last_health >= health_interval(rows):
                metrics = health(args.rm_url, hosts)
                snapshots.write(json.dumps(dict(time=now, metrics=metrics)) + '\n')
                last_health = now
            # The exact name and owner match also discovers an ID that the
            # client has not printed yet.
            for app in stage_applications(args.rm_url, names, user):
                row = names[app['name']]
                row['application_id'] = app['id']
                if row.get('state') != app['state']:
                    print(f'Job {row["index"]}: {app["state"]}', flush=True)
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
        print('Stopping this stage: ' + abort_reason, flush=True)
        manifest['abort_reason'] = abort_reason
        # Stop the clients first so nothing new is submitted during cleanup.
        try:
            stop_clients(processes)
        except Exception as exc:
            print(f'Could not confirm every job client stopped: {exc}', flush=True)
            manifest['client_stop_error'] = str(exc)
        # Known IDs come from this stage's own client logs and from exact
        # name and owner matches; cleanup looks again for late ones.
        known_ids = {row['application_id'] for row in rows if 'application_id' in row}
        try:
            cancelled, failed = cancel_stage_applications(args.rm_url, set(names), user, known_ids)
        except Exception as exc:
            cancelled, failed = [], sorted(known_ids)
            print(f'Cleanup stopped early: {exc}', flush=True)
        manifest.update(cancelled_application_ids=cancelled, cancel_failed_application_ids=failed)
        if failed:
            print('NOT CANCELLED, cancel these by hand: ' + ' '.join(failed), flush=True)
    finally:
        stop_clients(processes)
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
    batch.add_argument('--hosts', default=os.environ.get('HADOOP_HOSTS', ''),
                       help='comma-separated SSH targets: the controller first, then the three workers')
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
