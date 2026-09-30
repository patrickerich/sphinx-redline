"""Read-only access to the git repository that holds the documentation sources."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class GitError(Exception):
    """Raised when a git command fails unexpectedly."""


@dataclass(frozen=True)
class Hunk:
    """One ``-U0`` diff hunk: old lines replaced by new lines."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int


@dataclass
class FileDiff:
    """How one file changed between a commit and the working tree."""

    old_path: str | None
    new_path: str | None
    hunks: list[Hunk] = field(default_factory=list)

    def map_line(self, line: int) -> int | None:
        """Map a line number of the old file to the new file.

        Args:
            line: 1-based line number in the old file.

        Returns:
            The 1-based line number in the new file, or ``None`` if the line
            was changed or deleted.
        """
        if self.new_path is None:
            return None
        delta = 0
        for hunk in self.hunks:
            if hunk.old_count == 0:
                # Pure insertion after old line `old_start`.
                if hunk.old_start < line:
                    delta += hunk.new_count
                    continue
                break
            if line < hunk.old_start:
                break
            if line < hunk.old_start + hunk.old_count:
                return None
            delta += hunk.new_count - hunk.old_count
        return line + delta

    def map_range(self, first: int, last: int) -> tuple[int, int] | None:
        """Map a line range of the old file to the region it now occupies.

        Unchanged lines map to their new position. Lines that were edited map
        to the whole block of lines that replaced them, since that is where
        the edited text now is.

        Args:
            first: First line of the range in the old file (1-based).
            last: Last line of the range in the old file.

        Returns:
            The new ``(first, last)`` range, or ``None`` if every line of the
            range was deleted.
        """
        if self.new_path is None:
            return None
        mapped: list[int] = []
        for line in range(first, last + 1):
            new_line = self.map_line(line)
            if new_line is not None:
                mapped.append(new_line)
                continue
            for hunk in self.hunks:
                if hunk.old_start <= line < hunk.old_start + hunk.old_count and hunk.new_count:
                    mapped += [hunk.new_start, hunk.new_start + hunk.new_count - 1]
        return (min(mapped), max(mapped)) if mapped else None


class DiffIndex:
    """All file changes between one commit and the working tree."""

    _HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    def __init__(self, files: dict[str, FileDiff]) -> None:
        """Wrap parsed file diffs.

        Args:
            files: File diffs keyed by their path in the old commit.
        """
        self._files = files

    @classmethod
    def parse(cls, text: str) -> DiffIndex:
        """Parse the output of ``git diff -U0 -M``.

        Args:
            text: Unified diff text with ``a/`` and ``b/`` path prefixes.

        Returns:
            The parsed index. Files added since the commit are left out, since
            no comment can refer to them.
        """
        files: dict[str, FileDiff] = {}
        current: FileDiff | None = None
        in_hunks = False
        for line in text.splitlines():
            if line.startswith("diff --git "):
                current = FileDiff(old_path=None, new_path=None)
                in_hunks = False
            elif current is None:
                continue
            elif in_hunks:
                # Content lines: only a new hunk header matters here. A content
                # line may itself look like "+++ ..." or "rename to ...".
                if (match := cls._HUNK.match(line)) is not None:
                    current.hunks.append(cls._hunk(match))
                continue
            elif line.startswith("rename from "):
                current.old_path = line[len("rename from "):]
            elif line.startswith("rename to "):
                current.new_path = line[len("rename to "):]
            elif line.startswith("--- "):
                path = line[4:]
                current.old_path = None if path == "/dev/null" else path[2:]
            elif line.startswith("+++ "):
                path = line[4:]
                current.new_path = None if path == "/dev/null" else path[2:]
                if current.old_path is not None:
                    files[current.old_path] = current
            elif (match := cls._HUNK.match(line)) is not None:
                current.hunks.append(cls._hunk(match))
                in_hunks = True
            # A pure rename has no ---/+++ lines; record it once both paths are known.
            if current is not None and current.old_path and line.startswith("rename to "):
                files[current.old_path] = current
        return cls(files)

    @staticmethod
    def _hunk(match: re.Match[str]) -> Hunk:
        old_start, old_count, new_start, new_count = match.groups()
        return Hunk(
            old_start=int(old_start),
            old_count=1 if old_count is None else int(old_count),
            new_start=int(new_start),
            new_count=1 if new_count is None else int(new_count),
        )

    def file(self, path: str) -> FileDiff | None:
        """Return the diff for a path of the old commit, or ``None`` if unchanged."""
        return self._files.get(path)


class GitRepository:
    """Runs read-only git commands in one repository."""

    def __init__(self, root: Path) -> None:
        """Bind to a repository.

        Args:
            root: The top-level directory of the working tree.
        """
        self.root = root
        self._diffs: dict[str, DiffIndex | None] = {}

    @classmethod
    def discover(cls, path: Path) -> GitRepository | None:
        """Find the repository containing ``path``.

        Args:
            path: Any directory inside the working tree.

        Returns:
            The repository, or ``None`` if ``path`` is not in a git working
            tree or git is not installed.
        """
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return None
        if result.returncode != 0:
            return None
        return cls(Path(result.stdout.strip()))

    def _run(self, *args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", "-c", "core.quotePath=false", *args],
            cwd=self.root,
            input=stdin,
            capture_output=True,
            check=False,
        )

    def resolve(self, rev: str) -> str | None:
        """Resolve a revision to a commit id.

        Args:
            rev: Any revision git understands (commit id, branch, ref).

        Returns:
            The full commit id, or ``None`` if it does not exist locally.
        """
        result = self._run("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
        if result.returncode != 0:
            return None
        return result.stdout.decode().strip()

    def head(self) -> str | None:
        """Return the commit id of ``HEAD``, or ``None`` in an empty repository."""
        return self.resolve("HEAD")

    def relative_path(self, path: Path) -> str | None:
        """Express a file path relative to the repository root.

        Args:
            path: A file path.

        Returns:
            The POSIX-style relative path, or ``None`` if the file is outside
            the working tree.
        """
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return None

    def read_directory(self, rev: str, directory: str) -> dict[str, bytes]:
        """Read every file below a directory of a commit.

        Args:
            rev: The revision to read from.
            directory: Directory path inside that revision, without trailing slash.

        Returns:
            File contents keyed by path.

        Raises:
            GitError: If git cannot list or read the files.
        """
        listing = self._run("ls-tree", "-r", "-z", rev, "--", f"{directory}/")
        if listing.returncode != 0:
            raise GitError(listing.stderr.decode().strip())
        blobs: dict[str, str] = {}
        for entry in listing.stdout.decode(errors="replace").split("\0"):
            if not entry:
                continue
            meta, path = entry.split("\t", 1)
            _mode, kind, object_id = meta.split(" ")
            if kind == "blob":
                blobs[path] = object_id
        if not blobs:
            return {}
        # Request objects by id: paths may contain newlines, which would
        # break cat-file's line-based input.
        request = "".join(f"{object_id}\n" for object_id in blobs.values()).encode()
        batch = self._run("cat-file", "--batch", stdin=request)
        if batch.returncode != 0:
            raise GitError(batch.stderr.decode().strip())
        return dict(zip(blobs, self._split_batch(batch.stdout), strict=True))

    @staticmethod
    def _split_batch(output: bytes) -> list[bytes]:
        contents = []
        pos = 0
        while pos < len(output):
            header_end = output.index(b"\n", pos)
            _sha, _kind, size = output[pos:header_end].split(b" ")
            start = header_end + 1
            end = start + int(size)
            contents.append(output[start:end])
            pos = end + 1  # skip the newline after each object
        return contents

    def diff(self, commit: str) -> DiffIndex | None:
        """Return the changes from ``commit`` to the working tree.

        Args:
            commit: The commit a comment was made on.

        Returns:
            The diff index, or ``None`` if the commit is not available locally
            (for example in a shallow clone).
        """
        if commit not in self._diffs:
            self._diffs[commit] = self._load_diff(commit)
        return self._diffs[commit]

    def _load_diff(self, commit: str) -> DiffIndex | None:
        if self.resolve(commit) is None:
            return None
        result = self._run(
            "diff", "-U0", "-M", "--no-color", "--no-ext-diff",
            "--src-prefix=a/", "--dst-prefix=b/", commit, "--",
        )
        if result.returncode != 0:
            return None
        return DiffIndex.parse(result.stdout.decode(errors="replace"))
