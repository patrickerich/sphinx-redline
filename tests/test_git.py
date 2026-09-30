from sphinx_redline.git import DiffIndex, FileDiff, Hunk

DIFF = """\
diff --git a/docs/a.rst b/docs/a.rst
index 1111111..2222222 100644
--- a/docs/a.rst
+++ b/docs/a.rst
@@ -3,0 +4,2 @@ context
+new line 4
+new line 5
@@ -10,2 +12 @@ context
-old 10
-old 11
+new 12
diff --git a/docs/old.rst b/docs/new.rst
similarity index 100%
rename from docs/old.rst
rename to docs/new.rst
diff --git a/docs/gone.rst b/docs/gone.rst
deleted file mode 100644
index 3333333..0000000
--- a/docs/gone.rst
+++ /dev/null
@@ -1,2 +0,0 @@
-x
-y
diff --git a/docs/added.rst b/docs/added.rst
new file mode 100644
--- /dev/null
+++ b/docs/added.rst
@@ -0,0 +1 @@
+z
"""


def test_map_line_across_insertions_and_replacements() -> None:
    diff = DiffIndex.parse(DIFF).file("docs/a.rst")
    assert diff is not None
    assert [diff.map_line(n) for n in (1, 3, 4, 9, 10, 11, 12)] == [1, 3, 6, 11, None, None, 13]


def test_deletion_hunk_shifts_following_lines() -> None:
    diff = FileDiff("x", "x", [Hunk(old_start=5, old_count=2, new_start=4, new_count=0)])
    assert [diff.map_line(n) for n in (4, 5, 6, 7)] == [4, None, None, 5]


def test_rename_deletion_and_addition() -> None:
    index = DiffIndex.parse(DIFF)
    renamed = index.file("docs/old.rst")
    assert renamed is not None and renamed.new_path == "docs/new.rst"
    assert renamed.map_line(7) == 7
    gone = index.file("docs/gone.rst")
    assert gone is not None and gone.new_path is None and gone.map_line(1) is None
    assert index.file("docs/added.rst") is None
    assert index.file("docs/unchanged.rst") is None
