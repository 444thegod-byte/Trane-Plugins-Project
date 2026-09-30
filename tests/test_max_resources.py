"""Runtime discovery failures must not become false patch-object failures."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
import verify_patch as verifier  # noqa: E402


def make_resources(path: Path, names: tuple[str, ...] = ("buffer~",)) -> Path:
    init = path / "C74" / "init"
    init.mkdir(parents=True)
    for filename in (
        "max-objectlist.txt",
        "audio-objectlist.txt",
        "live-objectlist.txt",
        "jitter-objectlist.txt",
    ):
        (init / filename).write_text("", encoding="utf-8")
    (init / "max-objectlist.txt").write_text(
        "".join(f'max oblist "Objects" {name};\n' for name in names), encoding="utf-8"
    )
    return path


def make_live(directory: Path, filename: str, version: str) -> Path:
    bundle = directory / filename
    (bundle / "Contents").mkdir(parents=True)
    with (bundle / "Contents" / "Info.plist").open("wb") as f:
        plistlib.dump(
            {"CFBundleIdentifier": "com.ableton.live", "CFBundleShortVersionString": version}, f
        )
    return make_resources(
        bundle / "Contents" / "App-Resources" / "Max" / "Max.app" / "Contents" / "Resources"
    )


@pytest.fixture
def discovery_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    directories = (tmp_path / "Applications", tmp_path / "user" / "Applications")
    monkeypatch.delenv("MAX_RESOURCES", raising=False)
    monkeypatch.setattr(verifier.sys, "platform", "darwin")
    monkeypatch.setattr(verifier, "MACOS_APPLICATION_DIRS", directories)
    return directories


def test_explicit_resources_override_discovery_and_detect_typos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources = make_resources(tmp_path / "Max Resources")
    monkeypatch.setenv("MAX_RESOURCES", str(resources))
    monkeypatch.setattr(verifier.sys, "platform", "win32")
    database = verifier.load_object_db()
    valid = {"boxes": [{"box": {"maxclass": "newobj", "text": "buffer~ captured"}}]}
    assert verifier.check_objects_exist(valid, database, set()) == []
    invalid = {"boxes": [{"box": {"maxclass": "newobj", "text": "bufefr~ captured"}}]}
    errors = verifier.check_objects_exist(invalid, database, set())
    assert len(errors) == 1 and "bufefr~" in errors[0]


def test_invalid_explicit_path_does_not_fall_back_to_installed_live(
    tmp_path: Path, discovery_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    make_live(discovery_dirs[0], "Ableton Live 12 Suite.app", "12.4.6")
    monkeypatch.setenv("MAX_RESOURCES", str(tmp_path / "missing"))
    with pytest.raises(verifier.MaxRuntimeError, match="不存在"):
        verifier.load_object_db()


def test_empty_explicit_path_is_an_environment_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_RESOURCES", "")
    with pytest.raises(verifier.MaxRuntimeError, match="MAX_RESOURCES 为空"):
        verifier.load_object_db()


@pytest.mark.parametrize(
    "missing",
    ["max-objectlist.txt", "audio-objectlist.txt", "live-objectlist.txt", "jitter-objectlist.txt"],
)
def test_missing_required_object_list_is_an_environment_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    resources = make_resources(tmp_path / "Resources")
    (resources / "C74" / "init" / missing).unlink()
    monkeypatch.setenv("MAX_RESOURCES", str(resources))
    with pytest.raises(verifier.MaxRuntimeError, match=missing):
        verifier.load_object_db()


def test_empty_database_is_an_environment_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources = make_resources(tmp_path / "Resources", names=())
    monkeypatch.setenv("MAX_RESOURCES", str(resources))
    with pytest.raises(verifier.MaxRuntimeError, match="对象数据库为空"):
        verifier.load_object_db()


def test_all_existing_database_sources_remain_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources = make_resources(tmp_path / "Resources")
    (resources / "C74" / "init" / "max-objectmappings.txt").write_text(
        "max objectfile alias canonical;\n", encoding="utf-8"
    )
    docs = resources / "C74" / "docs" / "refpages"
    docs.mkdir(parents=True)
    (docs / "documented.maxref.xml").write_text('<c74object name="documented"/>', encoding="utf-8")
    (resources / "external.mxo").mkdir()
    (resources / "abstraction.maxpat").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("MAX_RESOURCES", str(resources))
    assert verifier.load_object_db() == {
        "buffer~", "alias", "canonical", "documented", "external", "abstraction"
    }


def test_discovery_uses_numeric_bundle_version_not_filename(
    discovery_dirs: tuple[Path, Path]
) -> None:
    make_live(discovery_dirs[0], "Ableton Live 99 Old.app", "9.10.2")
    newest = make_live(discovery_dirs[1], "Ableton Live 12 Suite.app", "12.4.6 (2026-09-10_build)")
    assert verifier.resolve_max_resources() == newest


def test_equal_versions_use_lexical_path_regardless_of_search_order(
    discovery_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    first = make_live(discovery_dirs[0], "Ableton Live 12 Suite.app", "12.4.6")
    make_live(discovery_dirs[1], "Ableton Live 12 Suite.app", "12.4.6")
    monkeypatch.setattr(verifier, "MACOS_APPLICATION_DIRS", tuple(reversed(discovery_dirs)))
    assert verifier.resolve_max_resources() == first


def test_incomplete_newest_runtime_does_not_silently_use_an_older_version(
    discovery_dirs: tuple[Path, Path]
) -> None:
    make_live(discovery_dirs[0], "Ableton Live 11 Suite.app", "11.3.43")
    newest = make_live(discovery_dirs[0], "Ableton Live 12 Suite.app", "12.4.6")
    (newest / "C74" / "init" / "live-objectlist.txt").unlink()
    with pytest.raises(verifier.MaxRuntimeError, match="live-objectlist.txt"):
        verifier.load_object_db()


def test_missing_live_installation_is_an_environment_error(
    discovery_dirs: tuple[Path, Path]
) -> None:
    with pytest.raises(verifier.MaxRuntimeError, match="未找到"):
        verifier.load_object_db()


@pytest.mark.parametrize("contents", [b"not a plist", b'<?xml version="1.0"?><plist><dict><'])
def test_corrupt_live_metadata_is_an_environment_error(
    discovery_dirs: tuple[Path, Path], contents: bytes
) -> None:
    resources = make_live(discovery_dirs[0], "Ableton Live 12 Suite.app", "12.4.6")
    plist = resources.parents[4] / "Info.plist"
    plist.write_bytes(contents)
    with pytest.raises(verifier.MaxRuntimeError, match="无法读取 Live 安装信息"):
        verifier.resolve_max_resources()


def test_other_platforms_require_explicit_resources(
    discovery_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(verifier.sys, "platform", "linux")
    with pytest.raises(verifier.MaxRuntimeError, match="MAX_RESOURCES"):
        verifier.load_object_db()


def test_cli_reports_missing_runtime_as_environment_error(tmp_path: Path) -> None:
    environment = dict(os.environ, MAX_RESOURCES=str(tmp_path / "missing"))
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tools" / "verify_patch.py")],
        env=environment, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "Max 运行时环境错误" in result.stderr
    assert "对象不存在" not in result.stderr
