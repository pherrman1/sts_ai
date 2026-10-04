"""Seed guard contract; fake commands only, never execute game seeds."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / 'tools/seed_guard.sh'


class SeedGuardTests(unittest.TestCase):
    def guard(self, *args):
        return subprocess.run(['bash', str(GUARD), *args], text=True, capture_output=True)

    def test_large_local_counts_and_argument_positions(self):
        for count in ('1', '128', '129', '2000', '1000000'):
            for command in (
                ['one_combat', 'bestbench', '1000', count, '0'],
                ['env', 'OMP_NUM_THREADS=2', './build/one_combat', 'wholecombatgen', count],
                ['python3', 'tools/check_replay.py', '1000', count],
                ['python', 'check_replay.py', '1000', count],
            ):
                with self.subTest(command=command):
                    result = self.guard('guard-only', *command)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_malformed_counts_fail_closed(self):
        for count in ('', '0', '000', '-1', 'no', '1.5', '1e3'):
            for command in (
                ['one_combat', 'bestbench', '1000', count],
                ['one_combat', 'wholecombatgen', count],
                ['python3', 'check_replay.py', '1000', count],
            ):
                with self.subTest(command=command):
                    result = self.guard('guard-only', *command)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('positive integer', result.stderr)
        self.assertNotEqual(self.guard('guard-only', 'one_combat', 'bestbench', '1000').returncode, 0)

    def test_usage_and_retired_option(self):
        for args in ((), ('guard-only',), ('--gcp-research', 'guard-only', 'true')):
            self.assertNotEqual(self.guard(*args).returncode, 0)

    def test_guard_only_does_not_execute_and_exec_preserves_argv_and_status(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'executed'
            command = ['bash', '-c', 'printf "%s" "$2" > "$1"; exit 7', 'test', str(marker), 'a b;$x']
            self.assertEqual(self.guard('guard-only', *command).returncode, 0)
            self.assertFalse(marker.exists())
            self.assertEqual(self.guard(*command).returncode, 7)
            self.assertEqual(marker.read_text(), 'a b;$x')

    def test_unlisted_commands_and_modes_pass_through(self):
        for command in (['true'], ['one_combat', 'run', '999999'], ['one_combat'], ['python3'],
                        ['python3', 'tools/verify/check_replay.py', '--self-test']):
            self.assertEqual(self.guard('guard-only', *command).returncode, 0)


if __name__ == '__main__':
    unittest.main()
