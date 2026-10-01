"""Exercise real macOS package metadata without installing a package."""
from __future__ import annotations

import os
import pathlib
import plistlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS packaging tools")


def make_build(tmp_path):
    build = tmp_path / "build"
    artefacts = build / "TranePlugin_artefacts" / "Release"
    for kind, name in (("VST3", "Trane.vst3"), ("AU", "Trane.component"), ("Standalone", "Trane.app")):
        contents = artefacts / kind / name / "Contents"
        (contents / "MacOS").mkdir(parents=True)
        (contents / "Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": "com.trane.test." + kind.lower(),
            "CFBundleExecutable": "Trane", "CFBundleVersion": "1",
            "CFBundleShortVersionString": "1", "CFBundlePackageType": "BNDL",
        }))
        binary = contents / "MacOS" / "Trane"
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o755)
    return build


def package(build, output):
    version = re.search(r"project\(Trane VERSION ([0-9.]+)", (ROOT / "CMakeLists.txt").read_text()).group(1)
    env = dict(os.environ, TRANE_BUILD_DIR=str(build), TRANE_INSTALLER_OUT=str(output),
               USER="a-different-package-builder")
    result = subprocess.run([str(ROOT / "tools" / "make_installers.sh"), version],
                            env=env, capture_output=True, text=True)
    return result, output / f"Trane-Plugins-v{version}.pkg"


def test_package_resolves_the_installing_user_home(tmp_path):
    result, archive = package(make_build(tmp_path), tmp_path / "installers")
    assert result.returncode == 0, result.stdout + result.stderr
    expanded = tmp_path / "expanded"
    subprocess.run(["pkgutil", "--expand-full", str(archive), str(expanded)], check=True)
    domains = ET.parse(expanded / "Distribution").find("domains")
    assert domains.attrib == {"enable_anywhere": "false", "enable_currentUserHome": "true",
                              "enable_localSystem": "false"}
    info_path = expanded / "Trane-Plugins.pkg" / "PackageInfo"
    assert "/Users/" not in info_path.read_text()
    info = ET.parse(info_path).getroot()
    assert info.get("install-location") == "/"
    assert info.get("identifier") == "com.trane.plugin"
    domains_result = subprocess.run(["installer", "-dominfo", "-pkg", str(archive)],
                                    check=True, capture_output=True, text=True)
    assert domains_result.stdout.strip() == "CurrentUserHomeDirectory"
    payload = expanded / "Trane-Plugins.pkg" / "Payload"
    assert (payload / "Library/Audio/Plug-Ins/VST3/Trane.vst3/Contents/MacOS/Trane").exists()
    assert (payload / "Library/Audio/Plug-Ins/Components/Trane.component/Contents/MacOS/Trane").exists()
    assert not (payload / "components.plist").exists()


def test_repackaging_preserves_existing_deliverables(tmp_path):
    output = tmp_path / "installers"
    output.mkdir()
    previous = output / "previous.pkg"
    previous.write_bytes(b"existing delivery")
    result, _ = package(make_build(tmp_path), output)
    assert result.returncode != 0
    assert previous.read_bytes() == b"existing delivery"
