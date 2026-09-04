import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "embed_git_info.py"


def run_git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL
    ).strip()


def run_script(output: Path, cwd: Path, extra_args=None) -> str:
    args = [sys.executable, str(SCRIPT)]
    if extra_args:
        args.extend(extra_args)
    args.append(str(output))
    subprocess.check_call(
        args, cwd=cwd
    )
    return output.read_text()


class GitInfoReproducibilityTest(TestCase):
    def test_developer_build_embeds_local_checkout_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            clone_a = root / "clone-a"
            clone_b = root / "clone-b"
            source.mkdir()

            run_git(source, "init")
            run_git(source, "config", "user.name", "Specter Test")
            run_git(source, "config", "user.email", "specter@example.invalid")
            (source / "payload.txt").write_text("same source\n")
            run_git(source, "add", "payload.txt")
            run_git(source, "commit", "-m", "fixture")
            commit = run_git(source, "rev-parse", "HEAD")

            run_git(root, "clone", str(source), str(clone_a))
            run_git(root, "clone", str(source), str(clone_b))

            run_git(clone_a, "checkout", "-b", "release-test")
            run_git(
                clone_a,
                "remote",
                "set-url",
                "origin",
                "git@example.invalid:fork/specter-diy.git",
            )

            run_git(clone_b, "checkout", "--detach", commit)
            run_git(
                clone_b,
                "remote",
                "set-url",
                "origin",
                "https://example.invalid/other/specter-diy.git",
            )

            content_a = run_script(root / "git-info-a.py", clone_a)
            content_b = run_script(root / "git-info-b.py", clone_b)

            self.assertNotEqual(content_a, content_b)
            self.assertIn(
                "REPOSITORY = 'git@example.invalid:fork/specter-diy.git'",
                content_a,
            )
            self.assertIn("BRANCH = 'release-test'", content_a)
            self.assertIn("COMMIT = %r" % commit, content_a)
            self.assertIn("WORKING_TREE = 'Clean'", content_a)
            self.assertIn(
                "REPOSITORY = 'https://example.invalid/other/specter-diy.git'",
                content_b,
            )
            self.assertIn("COMMIT = %r" % commit, content_b)

            (clone_a / "payload.txt").write_text("modified source\n")
            modified_content = run_script(root / "git-info-modified.py", clone_a)
            self.assertIn("WORKING_TREE = 'Modified'", modified_content)

    def test_developer_build_counts_non_ignored_untracked_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout = root / "checkout"
            checkout.mkdir()

            run_git(checkout, "init")
            run_git(checkout, "config", "user.name", "Specter Test")
            run_git(checkout, "config", "user.email", "specter@example.invalid")
            (checkout / "payload.txt").write_text("source\n")
            run_git(checkout, "add", "payload.txt")
            run_git(checkout, "commit", "-m", "fixture")

            (checkout / "new-source.txt").write_text("untracked source\n")
            content = run_script(root / "git-info.py", checkout)

            self.assertIn("WORKING_TREE = 'Modified'", content)

    def test_developer_build_ignores_ignored_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout = root / "checkout"
            checkout.mkdir()

            run_git(checkout, "init")
            run_git(checkout, "config", "user.name", "Specter Test")
            run_git(checkout, "config", "user.email", "specter@example.invalid")
            (checkout / ".gitignore").write_text("build/\n")
            (checkout / "payload.txt").write_text("source\n")
            run_git(checkout, "add", ".gitignore", "payload.txt")
            run_git(checkout, "commit", "-m", "fixture")

            build_dir = checkout / "build"
            build_dir.mkdir()
            (build_dir / "firmware.bin").write_bytes(b"generated")
            content = run_script(root / "git-info.py", checkout)

            self.assertIn("WORKING_TREE = 'Clean'", content)

    def test_developer_build_counts_changes_in_initialized_submodules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested_source = root / "nested-source"
            submodule_source = root / "submodule-source"
            checkout = root / "checkout"
            nested_source.mkdir()
            submodule_source.mkdir()
            checkout.mkdir()

            run_git(nested_source, "init")
            run_git(nested_source, "config", "user.name", "Specter Test")
            run_git(
                nested_source,
                "config",
                "user.email",
                "specter@example.invalid",
            )
            (nested_source / "payload.txt").write_text("nested source\n")
            run_git(nested_source, "add", "payload.txt")
            run_git(nested_source, "commit", "-m", "nested fixture")

            run_git(submodule_source, "init")
            run_git(submodule_source, "config", "user.name", "Specter Test")
            run_git(
                submodule_source,
                "config",
                "user.email",
                "specter@example.invalid",
            )
            (submodule_source / "payload.txt").write_text("submodule source\n")
            run_git(submodule_source, "add", "payload.txt")
            run_git(submodule_source, "commit", "-m", "submodule fixture")
            run_git(
                submodule_source,
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                str(nested_source),
                "dependencies/nested",
            )
            run_git(submodule_source, "commit", "-am", "add nested fixture")

            run_git(checkout, "init")
            run_git(checkout, "config", "user.name", "Specter Test")
            run_git(checkout, "config", "user.email", "specter@example.invalid")
            run_git(
                checkout,
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                str(submodule_source),
                "firmware",
            )
            run_git(checkout, "commit", "-am", "parent fixture")
            run_git(
                checkout,
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "update",
                "--init",
                "--recursive",
            )

            clean_content = run_script(root / "git-info-clean.py", checkout)
            self.assertIn("WORKING_TREE = 'Clean'", clean_content)

            nested_checkout = checkout / "firmware" / "dependencies" / "nested"
            (nested_checkout / "payload.txt").write_text("modified source\n")
            modified_content = run_script(root / "git-info-modified.py", checkout)
            self.assertIn("WORKING_TREE = 'Modified'", modified_content)

    def test_without_git_metadata_uses_stable_unknown_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "git-info.py"

            content = run_script(output, root)

            self.assertIn("REPOSITORY = 'unknown'", content)
            self.assertIn("BRANCH = 'unknown'", content)
            self.assertIn("COMMIT = 'unknown'", content)
            self.assertIn("WORKING_TREE = 'unknown'", content)

    def test_reproducible_build_output_is_source_acquisition_independent(self):
        """Reproducible builds must produce identical
        output from a git checkout and from a .git-less source archive."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout = root / "checkout"
            archive = root / "archive"
            checkout.mkdir()

            run_git(checkout, "init")
            run_git(checkout, "config", "user.name", "Specter Test")
            run_git(checkout, "config", "user.email", "specter@example.invalid")
            (checkout / "payload.txt").write_text("same source\n")
            run_git(checkout, "add", "payload.txt")
            run_git(checkout, "commit", "-m", "fixture")
            commit = run_git(checkout, "rev-parse", "HEAD")

            # A source archive: same files, no .git metadata.
            archive.mkdir()
            (archive / "payload.txt").write_text("same source\n")

            reproducible_args = ["--reproducible"]
            from_checkout = run_script(
                root / "a.py", checkout, reproducible_args
            )
            from_archive = run_script(root / "b.py", archive, reproducible_args)

            self.assertEqual(from_checkout, from_archive)
            self.assertIn("REPOSITORY = 'unknown'", from_checkout)
            self.assertIn("BRANCH = 'unknown'", from_checkout)
            self.assertIn("COMMIT = 'unknown'", from_checkout)
            self.assertIn("WORKING_TREE = 'unknown'", from_checkout)
            self.assertNotIn(commit, from_checkout)

    def test_make_forwards_reproducible_mode(self):
        developer_command = subprocess.check_output(
            ["make", "-n", "git-info"], cwd=REPO_ROOT, text=True
        )
        reproducible_command = subprocess.check_output(
            ["make", "-n", "git-info", "REPRODUCIBLE=1"],
            cwd=REPO_ROOT,
            text=True,
        )

        self.assertNotIn("--reproducible", developer_command)
        self.assertIn("--reproducible", reproducible_command)
