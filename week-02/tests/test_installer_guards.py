"""Exercise installer refusal paths without root, network access, or disk writes."""
import os
import grp
import pwd
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "hadoop-poc-rhel9.sh"
HELPERS = SCRIPT.read_text().split("# ---------- script begins ----------")[0]
STORAGE_COMMANDS = r'''
mountpoint() { [[ "${TEST_MOUNTED:-yes}" == yes ]]; }
findmnt() {
  case "$3" in
    MAJ:MIN)
      if [[ "$5" == / || "${TEST_ROOT_DISK:-no}" == yes ]]; then
        echo 8:1
      else
        echo 8:16
      fi ;;
    OPTIONS) echo "${TEST_MOUNT_OPTIONS:-rw,relatime}" ;;
    FSTYPE) echo "${TEST_FSTYPE:-xfs}" ;;
    *) exit 99 ;;
  esac
}
validate_storage
'''


class InstallerGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hadoop-guards-")
        self.addCleanup(self.tmp.cleanup)
        self.mount = Path(self.tmp.name) / "data"
        self.mount.mkdir()
        self.base = self.mount / "hadoop"

    def storage(self, **settings):
        env = dict(os.environ, DATA_MOUNT=str(self.mount), DATA_BASE=str(self.base))
        env.update(settings)
        return subprocess.run(
            ["bash", "-c", HELPERS + STORAGE_COMMANDS],
            env=env, text=True, capture_output=True, timeout=5,
        )

    def test_prepared_empty_filesystem_is_accepted(self):
        result = self.storage()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.base.exists(), "Validation must not create directories")

    def test_missing_mount_is_rejected(self):
        result = self.storage(TEST_MOUNTED="no")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Mount the assigned data disk", result.stderr)

    def test_root_filesystem_is_rejected(self):
        result = self.storage(TEST_ROOT_DISK="yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("root filesystem", result.stderr)

    def test_unusable_filesystems_are_rejected(self):
        for options in ("ro,relatime", "rw,noexec,nodev"):
            with self.subTest(options=options):
                result = self.storage(TEST_MOUNT_OPTIONS=options)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("YARN task execution", result.stderr)
        result = self.storage(TEST_FSTYPE="nfs4")
        self.assertNotEqual(result.returncode, 0)

    def test_existing_hdfs_data_is_preserved(self):
        self.base.mkdir()
        metadata = self.base / "VERSION"
        metadata.write_text("existing cluster metadata")
        result = self.storage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Existing data", result.stderr)
        self.assertEqual(metadata.read_text(), "existing cluster metadata")

    def test_path_outside_data_disk_is_rejected(self):
        result = self.storage(DATA_BASE=str(self.mount.parent / "elsewhere"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("beneath the data mount", result.stderr)

    def test_symlink_outside_data_disk_is_rejected(self):
        self.base.symlink_to(self.mount.parent, target_is_directory=True)
        result = self.storage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical", result.stderr)

    def test_file_instead_of_data_directory_is_rejected(self):
        self.base.write_text("keep me")
        result = self.storage()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.base.read_text(), "keep me")

    def test_input_eof_cannot_silently_accept_defaults(self):
        for command in ('answer="$(ask Settings default)"', 'ask_yn Install y'):
            with self.subTest(command=command):
                result = subprocess.run(
                    ["bash", "-c", HELPERS + command], input="", text=True,
                    capture_output=True, timeout=5,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Input ended", result.stderr)

    def test_help_does_not_require_root(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"], text=True, capture_output=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--check", result.stdout)

    def test_restrictive_umask_does_not_hide_data_ancestors(self):
        env = dict(
            os.environ,
            DATA_BASE=str(self.base),
            HADOOP_USER=pwd.getpwuid(os.getuid()).pw_name,
            HADOOP_GROUP=grp.getgrgid(os.getgid()).gr_name,
            HDFS_NAMENODE_DIR=str(self.base / "hdfs/nn"),
            HDFS_DATANODE_DIR=str(self.base / "hdfs/dn"),
            YARN_NM_LOCAL_DIR=str(self.base / "nm/local"),
            YARN_NM_LOG_DIR=str(self.base / "nm/log"),
            HADOOP_TMP_DIR=str(self.base / "tmp"),
        )
        result = subprocess.run(
            ["bash", "-c", HELPERS + "umask 077; create_data_dirs"],
            env=env, text=True, capture_output=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in [self.base, *self.base.rglob("*")]:
            self.assertEqual(path.stat().st_mode & 0o777, 0o750, str(path))
            self.assertEqual(path.stat().st_uid, os.getuid())


if __name__ == "__main__":
    unittest.main()
