import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
STATIC = ("redline.js", "redline.css", "keytool.html")


def test_wheel_contains_the_browser_files(tmp_path: Path) -> None:
    """A wheel without the static files installs fine but breaks every page."""
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--quiet", "-w", str(tmp_path), str(ROOT)],
        check=True,
    )
    (wheel,) = tmp_path.glob("sphinx_redline-*.whl")
    names = zipfile.ZipFile(wheel).namelist()
    for name in STATIC:
        assert f"sphinx_redline/static/redline/{name}" in names
    assert any(n.endswith(".dist-info/licenses/LICENSE") for n in names)
