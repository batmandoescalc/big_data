"""Safety and evidence checks; never connect to the cluster."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch


def module(name):
    path = Path(__file__).resolve().parents[1] / 'scripts' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


burst = module('hadoop_burst')
probe = module('memory_probe')


class ExperimentSafetyTests(unittest.TestCase):
    """Experiments reject unsafe paths/caps and validate complete register evidence."""

    def test_reject_other_users_and_traversal(self):
        for path in ('/user/bob/output', '/user/alice/../bob/output', '/tmp/output'):
            with self.assertRaises(ValueError):
                burst.owned_path(path, 'alice')
        self.assertEqual(burst.owned_path('/user/alice/week09/', 'alice'),
                         '/user/alice/week09')

    def test_register_equality_is_independent_of_output_order(self):
        left = burst.canonical_registers('1\t5\n0\t3\n')
        right = burst.canonical_registers('0\t3\n1\t5\n')
        self.assertEqual(burst.checksum(left), burst.checksum(right))

    def test_duplicate_registers_are_rejected(self):
        with self.assertRaises(ValueError):
            burst.canonical_registers('0\t3\n0\t3\n')

    def test_scheduled_time_requires_explicit_timezone(self):
        with self.assertRaises(ValueError):
            burst.start_epoch('2026-11-11T12:05:00')
        self.assertEqual(burst.start_epoch('2026-11-11T12:05:00-05:00'),
                         burst.start_epoch('2026-11-11T17:05:00Z'))

    def test_probe_refuses_unlimited_or_wrong_memory_and_swap(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for maximum, swap in [('max', '0'), (str(256 * 1024**2), '0'),
                                  (str(128 * 1024**2), 'max')]:
                (folder / 'memory.max').write_text(maximum)
                (folder / 'memory.swap.max').write_text(swap)
                with self.assertRaises(RuntimeError):
                    probe.validate_limits(folder, 128)
            (folder / 'memory.max').write_text(str(128 * 1024**2))
            (folder / 'memory.swap.max').write_text('0')
            probe.validate_limits(folder, 128)

    def test_remote_command_uses_posix_paths_and_bounded_resources(self):
        with patch.object(burst, 'TRANSPORT', 'alice@controller'), \
             patch.object(burst, 'REMOTE_ROOT', '/home/alice/project'), \
             patch.object(burst, 'HADOOP_HOME', '/opt/hadoop'), \
             patch.object(burst, 'run', return_value='/opt/hadoop/streaming.jar\n'):
            command = burst.command_for('/user/alice/input', '/user/alice/out', 'test', 'alice')
        self.assertIn('mapreduce.map.memory.mb=1024', command)
        self.assertIn('yarn.app.mapreduce.am.resource.mb=1024', command)
        self.assertIn('yarn.app.mapreduce.am.staging-dir=/user/alice/.staging', command)
        self.assertIn('/home/alice/project/week-07/scripts/hadoop/fm_mapper.py',
                      command[command.index('-files') + 1])

    def test_unhealthy_cluster_rejects_submission(self):
        with patch.object(burst, 'api', return_value={'clusterMetrics':
                          dict(activeNodes=2, unhealthyNodes=1, lostNodes=0)}):
            with self.assertRaises(RuntimeError):
                burst.health('unused', [])

    def test_low_available_vm_memory_rejects_submission(self):
        output = SimpleNamespace(stdout='MemAvailable: 1024 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n')
        with patch.object(burst, 'api', return_value={'clusterMetrics':
                          dict(activeNodes=3, unhealthyNodes=0, lostNodes=0)}), \
             patch.object(burst.subprocess, 'run', return_value=output):
            with self.assertRaises(RuntimeError):
                burst.health('unused', ['alice@worker'])

    def test_one_ssh_timeout_is_retried(self):
        timeout = burst.subprocess.TimeoutExpired('ssh', 20)
        with patch.object(burst.subprocess, 'run', side_effect=[timeout,
                          SimpleNamespace(stdout='healthy snapshot')]) as external:
            self.assertEqual(burst.host_snapshot('worker'), 'healthy snapshot')
            self.assertEqual(external.call_count, 2)
            self.assertEqual(external.call_args.kwargs['stdin'], burst.subprocess.DEVNULL)

    def test_background_ssh_does_not_read_the_interactive_console(self):
        command = burst.ssh_prefix()
        self.assertIn('-n', command)
        self.assertIn('-T', command)
        with patch.object(burst.subprocess, 'run', return_value=SimpleNamespace(stdout='ok')) as external:
            self.assertEqual(burst.run(['true']), 'ok')
            self.assertEqual(external.call_args.kwargs['stdin'], burst.subprocess.DEVNULL)

    def test_repeated_ssh_timeouts_still_fail_closed(self):
        timeout = burst.subprocess.TimeoutExpired('ssh', 20)
        with patch.object(burst.subprocess, 'run', side_effect=timeout) as external:
            with self.assertRaises(burst.subprocess.TimeoutExpired):
                burst.host_snapshot('worker')
            self.assertEqual(external.call_count, 2)

    def test_health_abort_kills_only_the_recorded_experiment_application(self):
        events = []

        class Process:
            stdout = iter(['Submitted application application_1_1\n'])
            returncode = None
            def poll(self):
                return self.returncode
            def terminate(self):
                events.append('client stopped')
                self.returncode = -15
            def wait(self, timeout=None):
                return self.returncode

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = launch_args(root, 'abort-test', 1)
            with patch.object(burst, 'TRANSPORT', None), \
                 patch.object(burst, 'identity', return_value='alice'), \
                 patch.object(burst, 'command_for', return_value=['fake-hadoop']), \
                 patch.object(burst, 'exists', return_value=False), \
                 patch.object(burst, 'run', return_value=''), \
                 patch.object(burst, 'health', side_effect=[{}, RuntimeError('unhealthy')]), \
                 patch.object(burst, 'api', return_value={}), \
                 patch.object(burst.time, 'sleep'), \
                 patch.object(burst.subprocess, 'Popen', return_value=Process()), \
                 patch.object(burst.subprocess, 'run', side_effect=lambda *a, **k: (
                     events.append('application cancelled'),
                     SimpleNamespace(returncode=0))[1]) as external, \
                 patch.object(burst.threading, 'Thread', ImmediateThread):
                self.assertEqual(burst.launch(args), 1)
            external.assert_called_once_with(['yarn', 'application', '-kill', 'application_1_1'],
                                              stdin=burst.subprocess.DEVNULL, timeout=30)
            self.assertEqual(events, ['client stopped', 'application cancelled'])
            manifest = json.loads((root / 'evidence' / 'manifest.json').read_text())
            self.assertEqual(manifest['cancelled_application_ids'], ['application_1_1'])
            self.assertEqual(manifest['cancel_failed_application_ids'], [])


class ClientBudgetTests(unittest.TestCase):
    """A stage is refused when its job clients would not fit in the controller's memory, and health is checked more often while jobs launch."""

    def check(self, available_mib, clients):
        output = SimpleNamespace(stdout=f'MemAvailable: {available_mib * 1024} kB\n')
        with patch.object(burst, 'api', return_value={'clusterMetrics':
                          dict(activeNodes=3, unhealthyNodes=0, lostNodes=0)}), \
             patch.object(burst.subprocess, 'run', return_value=output):
            return burst.health('unused', ['alice@controller', 'alice@worker'], clients)

    def test_clients_that_fit_are_counted_above_the_guard(self):
        allowance = burst.CLIENT_ALLOWANCE_KB
        self.assertEqual(burst.clients_that_fit(burst.MIN_AVAILABLE_KB + 3 * allowance), 3)
        self.assertEqual(burst.clients_that_fit(burst.MIN_AVAILABLE_KB + 3 * allowance - 1), 2)
        self.assertEqual(burst.clients_that_fit(burst.MIN_AVAILABLE_KB - 1), 0)

    def test_stage_that_fits_is_allowed(self):
        self.check(2048 + 4 * 256, 4)

    def test_stage_that_does_not_fit_is_refused_and_says_how_many_would(self):
        # The idle controller measured before the 15-each round had 5,655 MiB.
        with self.assertRaisesRegex(RuntimeError, 'only 14 would fit'):
            self.check(5655, 15)

    def test_running_stage_is_held_to_the_guard_alone(self):
        self.check(2048, 0)

    def test_health_is_checked_more_often_until_every_job_has_reached_yarn(self):
        launching = [dict(application_id='application_1_1'), dict()]
        launched = [dict(application_id='application_1_1'), dict(application_id='application_1_2')]
        self.assertLess(burst.health_interval(launching), burst.health_interval(launched))


class ImmediateThread:
    """Runs the reader inline, so a fake client's output is read before launch polls."""

    def __init__(self, target, args, **kwargs):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)

    def join(self, **kwargs):
        pass


def launch_args(root, stage, jobs):
    expected = root / 'expected.json'
    expected.write_text(json.dumps({i: 0 for i in range(128)}))
    return SimpleNamespace(hdfs_input='/user/alice/input', hdfs_output='/user/alice/out',
                           stage=stage, start_at=None, expected=expected, jobs=jobs,
                           execute=True, hosts='a,b,c,d', rm_url='unused', timeout=10,
                           evidence=root / 'evidence')


def gone(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


class SingleConnectionBatchTests(unittest.TestCase):
    """A remote batch uses one SSH connection, keeps each job's result apart, and stops every client with it."""

    def test_script_starts_every_job_in_the_background_and_watches_stdin(self):
        command = burst.batch_command([['hadoop', 'jar', 'a b.jar'], ['hadoop', 'jar', 'c.jar']])
        self.assertEqual(command[:4], ['setsid', '-w', 'bash', '-c'])
        script = command[4]
        self.assertEqual(script.count("/' &"), 2)
        self.assertIn("'a b.jar'", script)
        self.assertIn('s/^/JOB1 /', script)
        self.assertIn('<&0 &', script)

    def test_batch_connection_keeps_stdin_and_other_ssh_calls_do_not(self):
        with patch.object(burst, 'TRANSPORT', 'alice@controller'):
            self.assertNotIn('-n', burst.execution(['true'], stdin=True))
            self.assertIn('-n', burst.execution(['true']))

    def test_lines_and_exit_codes_reach_the_right_job(self):
        clients = [burst.BatchClient(None) for _ in range(2)]
        seen, stray = [], []
        burst.route_batch_output(iter(['Authorized uses only.\n',
                                       'JOB1 Submitted application application_1_7\n',
                                       'JOB0 BURST_EXIT 0\n', 'JOB1 BURST_EXIT 2\n']),
                                 clients, lambda index, line: seen.append((index, line)), stray.append)
        self.assertEqual(seen, [(1, 'Submitted application application_1_7\n')])
        self.assertEqual(stray, ['Authorized uses only.\n'])
        self.assertEqual([client.poll() for client in clients], [0, 2])

    def test_dropped_connection_fails_every_unfinished_job(self):
        clients = [burst.BatchClient(None) for _ in range(3)]
        burst.route_batch_output(iter(['JOB0 BURST_EXIT 0\n']), clients,
                                 lambda index, line: None, lambda line: None)
        self.assertEqual([client.poll() for client in clients], [0, 255, 255])

    def remote_launch(self, root, jobs, lines, health):
        events = []

        class Connection:
            stdout = iter(lines)
            stdin = SimpleNamespace(close=lambda: events.append('stdin closed'))
            def wait(self, timeout=None):
                return 0

        registers = ''.join(f'{i}\t0\n' for i in range(128))
        finished = {'app': dict(state='FINISHED', finalStatus='SUCCEEDED')}
        with patch.object(burst, 'TRANSPORT', 'alice@controller'), \
             patch.object(burst, 'identity', return_value='alice'), \
             patch.object(burst, 'command_for', return_value=['fake-hadoop']), \
             patch.object(burst, 'exists', return_value=False), \
             patch.object(burst, 'run', side_effect=lambda command: registers if 'dfs' in command else str(time.time())), \
             patch.object(burst, 'health', side_effect=health), \
             patch.object(burst, 'api', side_effect=lambda base, endpoint: finished if '/' in endpoint else {}), \
             patch.object(burst.time, 'sleep'), \
             patch.object(burst.subprocess, 'Popen', return_value=Connection()) as popen, \
             patch.object(burst.subprocess, 'run', side_effect=lambda *a, **k: (
                 events.append('application cancelled'), SimpleNamespace(returncode=0))[1]), \
             patch.object(burst.threading, 'Thread', ImmediateThread):
            code = burst.launch(launch_args(root, 'remote', jobs))
        return code, popen, events, json.loads((root / 'evidence' / 'manifest.json').read_text())

    def test_ten_remote_jobs_open_one_connection_with_stdin_held(self):
        lines = ([f'JOB{i} Submitted application application_1_{i}\n' for i in range(10)]
                 + [f'JOB{i} BURST_EXIT 0\n' for i in range(10)])
        with tempfile.TemporaryDirectory() as directory:
            code, popen, _, manifest = self.remote_launch(Path(directory), 10, lines, lambda *a: {})
        self.assertEqual(code, 0)
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(popen.call_args.kwargs['stdin'], burst.subprocess.PIPE)
        self.assertNotIn('-n', popen.call_args.args[0])
        self.assertEqual([job['application_id'] for job in manifest['jobs']],
                         [f'application_1_{i}' for i in range(10)])
        self.assertTrue(all(job['registers_match'] for job in manifest['jobs']))

    def test_remote_abort_closes_stdin_before_cancelling(self):
        class Unfinished:
            # The clients are still running: the stream stays open until stdin closes.
            def __iter__(self):
                return iter(['JOB0 Submitted application application_1_1\n'])

        outcomes = iter([{}, RuntimeError('unhealthy')])

        def health(*args):
            outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(burst, 'route_batch_output',
                              side_effect=lambda stream, clients, on_line, stray:
                              [on_line(0, line[5:]) for line in stream]):
                code, _, events, manifest = self.remote_launch(Path(directory), 1, Unfinished(), health)
        self.assertEqual(code, 1)
        self.assertEqual(events[:2], ['stdin closed', 'application cancelled'])
        self.assertEqual(manifest['cancelled_application_ids'], ['application_1_1'])


@unittest.skipUnless(os.name == 'posix' and all(map(shutil.which, ('bash', 'sed', 'setsid'))),
                     'needs bash, sed and setsid')
class BatchScriptProcessTests(unittest.TestCase):
    """The generated batch script, run by a real shell with stand-in clients, leaves no client alive once stopped."""

    def start(self, commands):
        process = subprocess.Popen(burst.batch_command(commands), text=True,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.addCleanup(process.kill)
        self.addCleanup(process.stdout.close)
        return process

    def client_pids(self, process, count):
        return [int(process.stdout.readline().split()[1]) for _ in range(count)]

    def assert_all_gone(self, process, pids):
        process.wait(timeout=20)
        deadline = time.monotonic() + 5
        while not all(map(gone, pids)) and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertEqual([pid for pid in pids if not gone(pid)], [])

    def test_lines_are_tagged_and_each_exit_status_is_reported(self):
        process = self.start([['sh', '-c', 'echo first; exit 0'],
                              ['sh', '-c', 'echo second >&2; exit 3']])
        # stdin stays open: the script ends by itself once every client has.
        self.assertEqual(sorted(process.stdout.read().splitlines()),
                         ['JOB0 BURST_EXIT 0', 'JOB0 first', 'JOB1 BURST_EXIT 3', 'JOB1 second'])
        process.wait(timeout=20)

    def test_closing_stdin_stops_every_client(self):
        process = self.start([['sh', '-c', 'echo $$; exec sleep 300']] * 3)
        pids = self.client_pids(process, 3)
        self.assertFalse(any(map(gone, pids)))
        process.stdin.close()
        self.assert_all_gone(process, pids)

    def test_a_signal_stops_every_client(self):
        process = self.start([['sh', '-c', 'echo $$; exec sleep 300']] * 3)
        pids = self.client_pids(process, 3)
        process.terminate()
        self.assert_all_gone(process, pids)

    def test_client_that_ignores_the_stop_signal_is_killed(self):
        stubborn = ['bash', '-c', 'trap "" TERM; echo $$; while :; do sleep 1; done']
        with patch.object(burst, 'STOP_GRACE_SECONDS', 1):
            process = self.start([stubborn])
        pids = self.client_pids(process, 1)
        process.stdin.close()
        # SIGKILL takes the script too, so only the client's absence is checked.
        process.wait(timeout=20)
        deadline = time.monotonic() + 5
        while not gone(pids[0]) and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertTrue(gone(pids[0]))


def listing(*apps):
    return {'apps': {'app': [dict(id=i, name=n, user=u, state=s) for i, n, u, s in apps]}}


class AbortCleanupTests(unittest.TestCase):
    """An aborted stage cancels every application it owns, including late ones, and no one else's."""

    def cancel(self, listings, known=(), results=None):
        results = results or SimpleNamespace(returncode=0)
        with patch.object(burst, 'TRANSPORT', None), \
             patch.object(burst, 'api', side_effect=listings), \
             patch.object(burst.time, 'sleep'), \
             patch.object(burst.subprocess, 'run', **(
                 dict(side_effect=results) if isinstance(results, list)
                 else dict(return_value=results))) as external:
            outcome = burst.cancel_stage_applications('unused', {'week09-s-alice-0', 'week09-s-alice-1'},
                                                      'alice', set(known))
        return outcome, [call.args[0][-1] for call in external.call_args_list]

    def test_application_that_appears_after_the_abort_is_still_cancelled(self):
        late = listing(('application_1_2', 'week09-s-alice-1', 'alice', 'ACCEPTED'))
        (cancelled, failed), killed = self.cancel([{}, late] + [late] * burst.CLEANUP_POLLS,
                                                  known=['application_1_1'])
        self.assertEqual(killed, ['application_1_1', 'application_1_2'])
        self.assertEqual((cancelled, failed), (['application_1_1', 'application_1_2'], []))

    def test_same_name_from_another_user_and_other_names_are_never_cancelled(self):
        apps = listing(('application_1_5', 'week09-s-alice-0', 'bob', 'RUNNING'),
                       ('application_1_6', 'week09-s-alice-00', 'alice', 'RUNNING'),
                       ('application_1_7', 'week09-s-alice-0', 'alice', 'RUNNING'))
        _, killed = self.cancel([apps] * burst.CLEANUP_POLLS)
        self.assertEqual(killed, ['application_1_7'])

    def test_finished_application_is_left_alone(self):
        apps = listing(('application_1_1', 'week09-s-alice-0', 'alice', 'FINISHED'))
        _, killed = self.cancel([apps] * burst.CLEANUP_POLLS, known=['application_1_1'])
        self.assertEqual(killed, [])

    def test_one_timed_out_cancel_does_not_skip_the_rest_and_is_reported(self):
        timeout = burst.subprocess.TimeoutExpired('yarn', 30)
        done = SimpleNamespace(returncode=0)
        results = [timeout, done] + [timeout] * (burst.CLEANUP_POLLS - 1)
        (cancelled, failed), killed = self.cancel([{}] * burst.CLEANUP_POLLS,
                                                  known=['application_1_1', 'application_1_2'],
                                                  results=results)
        self.assertEqual(killed[:2], ['application_1_1', 'application_1_2'])
        self.assertEqual((cancelled, failed), (['application_1_2'], ['application_1_1']))

    def test_unreachable_resourcemanager_still_cancels_known_applications(self):
        (cancelled, failed), killed = self.cancel(OSError('no route'), known=['application_1_1'])
        self.assertEqual((cancelled, failed, killed),
                         (['application_1_1'], [], ['application_1_1']))


if __name__ == '__main__':
    unittest.main()
