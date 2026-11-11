"""Safety and evidence checks; never connect to the cluster."""
import importlib.util
from pathlib import Path
import tempfile
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

    def test_next_connection_can_start_after_authentication_without_waiting_for_job(self):
        ready = burst.threading.Event()
        ready.set()
        process = SimpleNamespace(poll=lambda: None)
        burst.wait_for_authentication(process, ready, timeout=.01)

    def test_missing_authentication_acknowledgement_fails(self):
        ready = burst.threading.Event()
        with self.assertRaises(RuntimeError):
            burst.wait_for_authentication(SimpleNamespace(poll=lambda: 255), ready, timeout=.01)
        with self.assertRaises(TimeoutError):
            burst.wait_for_authentication(SimpleNamespace(poll=lambda: None), ready, timeout=.001)

    def test_remote_submission_signals_authentication_before_hadoop(self):
        with patch.object(burst, 'TRANSPORT', 'alice@controller'):
            command = burst.job_execution(['hadoop', 'jar', '/safe/job.jar'])
        self.assertLess(command[-1].index(burst.SSH_READY), command[-1].index('exec hadoop'))

    def test_repeated_ssh_timeouts_still_fail_closed(self):
        timeout = burst.subprocess.TimeoutExpired('ssh', 20)
        with patch.object(burst.subprocess, 'run', side_effect=timeout) as external:
            with self.assertRaises(burst.subprocess.TimeoutExpired):
                burst.host_snapshot('worker')
            self.assertEqual(external.call_count, 2)

    def test_health_abort_kills_only_the_recorded_experiment_application(self):
        class Process:
            stdout = iter(['Submitted application application_1_1\n'])
            returncode = None
            def poll(self):
                return self.returncode
            def terminate(self):
                self.returncode = -15
            def wait(self, timeout=None):
                return self.returncode

        class ImmediateThread:
            def __init__(self, target, args, **kwargs):
                self.target, self.args = target, args
            def start(self):
                self.target(*self.args)
            def join(self, **kwargs):
                pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = root / 'expected.json'
            expected.write_text(__import__('json').dumps({i: 0 for i in range(128)}))
            args = SimpleNamespace(hdfs_input='/user/alice/input', hdfs_output='/user/alice/out',
                                   stage='abort-test', start_at=None, expected=expected, jobs=1,
                                   execute=True, hosts='a,b,c,d', rm_url='unused', timeout=10,
                                   evidence=root / 'evidence')
            with patch.object(burst, 'TRANSPORT', None), \
                 patch.object(burst, 'identity', return_value='alice'), \
                 patch.object(burst, 'command_for', return_value=['fake-hadoop']), \
                 patch.object(burst, 'exists', return_value=False), \
                 patch.object(burst, 'run', return_value=''), \
                 patch.object(burst, 'health', side_effect=[{}, RuntimeError('unhealthy')]), \
                 patch.object(burst.subprocess, 'Popen', return_value=Process()), \
                 patch.object(burst.subprocess, 'run') as external, \
                 patch.object(burst.threading, 'Thread', ImmediateThread):
                self.assertEqual(burst.launch(args), 1)
            external.assert_called_once_with(['yarn', 'application', '-kill', 'application_1_1'],
                                              stdin=burst.subprocess.DEVNULL, timeout=30)


if __name__ == '__main__':
    unittest.main()
