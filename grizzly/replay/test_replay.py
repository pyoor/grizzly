# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
# pylint: disable=protected-access
"""
unit tests for grizzly.replay
"""
from os.path import join as pathjoin

from pytest import raises

from sapphire import Sapphire, SERVED_ALL, SERVED_REQUEST
from .replay import ReplayManager
from ..common import Report, Status, TestCase
from ..target import Target, TargetLaunchError


def _fake_save_logs_result(result_logs, meta=False):  # pylint: disable=unused-argument
    """write fake log data to disk"""
    with open(pathjoin(result_logs, "log_stderr.txt"), "w") as log_fp:
        log_fp.write("STDERR log\n")
    with open(pathjoin(result_logs, "log_stdout.txt"), "w") as log_fp:
        log_fp.write("STDOUT log\n")
    with open(pathjoin(result_logs, "log_asan_blah.txt"), "w") as log_fp:
        log_fp.write("==1==ERROR: AddressSanitizer: ")
        log_fp.write("SEGV on unknown address 0x0 (pc 0x0 bp 0x0 sp 0x0 T0)\n")
        log_fp.write("    #0 0xbad000 in foo /file1.c:123:234\n")
        log_fp.write("    #1 0x1337dd in bar /file2.c:1806:19\n")

def test_replay_01(mocker):
    """test ReplayManager.cleanup()"""
    replay = ReplayManager([], mocker.Mock(spec=Sapphire), mocker.Mock(spec=Target), [mocker.Mock()])
    replay._reports_expected = {"A":  mocker.Mock(spec=Report)}
    replay._reports_other = {"B":  mocker.Mock(spec=Report)}
    replay.status = mocker.Mock(spec=Status)
    ereport = tuple(replay.reports)[0]
    oreport = tuple(replay.other_reports)[0]
    replay.cleanup()
    assert ereport.cleanup.call_count == 1
    assert oreport.cleanup.call_count == 1
    assert replay.status.cleanup.call_count == 1

def test_replay_02(mocker, tmp_path):
    """test ReplayManager.run() - no repro"""
    mocker.patch("grizzly.replay.replay.grz_tmp", return_value=str(tmp_path))
    server = mocker.Mock(spec=Sapphire, port=0x1337)
    server.serve_path.return_value = (SERVED_ALL, ["index.html"])
    target = mocker.Mock(spec=Target)
    target.RESULT_NONE = Target.RESULT_NONE
    target.closed = True
    target.detect_failure.return_value = Target.RESULT_NONE
    target.forced_close = True
    target.rl_reset = 1
    with TestCase("land_page.html", "redirect.html", "test-adapter") as testcase:
        with ReplayManager([], server, target, use_harness=True) as replay:
            assert not replay.run([testcase])
            assert replay.status.ignored == 0
            assert replay.status.iteration == 1
            assert replay.status.results == 0
            assert not replay.reports
        assert not any(tmp_path.glob("*"))

def test_replay_03(mocker, tmp_path):
    """test ReplayManager.run() - successful repro"""
    mocker.patch("grizzly.replay.replay.grz_tmp", return_value=str(tmp_path))
    server = mocker.Mock(spec=Sapphire, port=0x1337)
    server.serve_path.return_value = (SERVED_ALL, ["index.html"])
    target = mocker.Mock(spec=Target)
    target.RESULT_FAILURE = Target.RESULT_FAILURE
    target.binary = "C:\\fake_bin"
    target.detect_failure.return_value = Target.RESULT_FAILURE
    target.save_logs = _fake_save_logs_result
    with TestCase("land_page.html", "redirect.html", "test-adapter") as testcase:
        with ReplayManager([], server, target, use_harness=False) as replay:
            assert replay.run([testcase])
            assert replay.status.ignored == 0
            assert replay.status.iteration == 1
            assert replay.status.results == 1
            assert len(replay.reports) == 1
            assert not replay.other_reports
        assert not any(tmp_path.glob("*"))

def test_replay_04(mocker):
    """test ReplayManager.run() - Error (landing page not requested/served)"""
    server = mocker.Mock(spec=Sapphire, port=0x1337)
    server.serve_path.return_value = (SERVED_REQUEST, ["x"])
    target = mocker.Mock(spec=Target)
    target.RESULT_NONE = Target.RESULT_NONE
    target.detect_failure.return_value = Target.RESULT_NONE
    testcases = [mocker.Mock(spec=TestCase, env_vars=[], landing_page="index.html", optional=[])]
    with ReplayManager([], server, target, use_harness=False) as replay:
        assert not replay.run(testcases, repeat=2)
        assert replay.status.ignored == 0
        assert replay.status.iteration == 1
        assert replay.status.results == 0
        assert not replay.reports
        assert not replay.other_reports
    assert target.check_relaunch.call_count == 0

def test_replay_05(mocker):
    """test ReplayManager.run() - ignored"""
    server = mocker.Mock(spec=Sapphire, port=0x1337)
    server.serve_path.return_value = (SERVED_ALL, ["index.html"])
    target = mocker.Mock(spec=Target)
    target.RESULT_IGNORED = Target.RESULT_IGNORED
    target.detect_failure.return_value = Target.RESULT_IGNORED
    testcases = [mocker.Mock(spec=TestCase, env_vars=[], landing_page="index.html", optional=[])]
    with ReplayManager([], server, target, use_harness=False) as replay:
        assert not replay.run(testcases)
        assert replay.status.ignored == 1
        assert replay.status.iteration == 1
        assert replay.status.results == 0
        assert not replay.reports
        assert not replay.other_reports

def test_replay_06(mocker):
    """test ReplayManager.run() - early exit"""
    server = mocker.Mock(spec=Sapphire, port=0x1337)
    server.serve_path.return_value = (SERVED_ALL, ["index.html"])
    target = mocker.Mock(spec=Target, binary="path/fake_bin")
    target.RESULT_FAILURE = Target.RESULT_FAILURE
    target.RESULT_IGNORED = Target.RESULT_IGNORED
    target.RESULT_NONE = Target.RESULT_NONE
    target.save_logs = _fake_save_logs_result
    testcases = [mocker.Mock(spec=TestCase, env_vars=[], landing_page="index.html", optional=[])]
    # early failure
    target.detect_failure.side_effect = [Target.RESULT_FAILURE, Target.RESULT_IGNORED, Target.RESULT_NONE]
    with ReplayManager([], server, target, use_harness=False) as replay:
        assert not replay.run(testcases, repeat=4, min_results=3)
        assert replay.status.iteration == 3
        assert replay.status.results == 1
        assert replay.status.ignored == 1
        assert len(replay.reports) == 1
    # early success
    target.detect_failure.side_effect = [Target.RESULT_FAILURE, Target.RESULT_IGNORED, Target.RESULT_FAILURE]
    with ReplayManager([], server, target, use_harness=False) as replay:
        assert replay.run(testcases, repeat=4, min_results=2)
        assert replay.status.iteration == 3
        assert replay.status.results == 2
        assert replay.status.ignored == 1
        assert len(replay._reports_expected) == 1
        assert not replay._reports_other
        assert len(replay.reports) == 1

def test_replay_07(mocker, tmp_path):
    """test ReplayManager.run() - test signatures"""
    report = mocker.patch("grizzly.replay.replay.Report", autospec=True)
    mocker.patch("grizzly.replay.replay.mkdtemp", autospec=True, return_value=str(tmp_path))
    report_0 = mocker.Mock(spec=Report)
    report_0.crash_info.return_value.createShortSignature.return_value = "No crash detected"
    report_1 = mocker.Mock(spec=Report, major="0123abcd", minor="01239999")
    report_1.crash_info.return_value.createShortSignature.return_value = "[@ test1]"
    report_2 = mocker.Mock(spec=Report, major="0123abcd", minor="abcd9876")
    report_2.crash_info.return_value.createShortSignature.return_value = "[@ test2]"
    report.from_path.side_effect = (report_0, report_1, report_2)
    server = mocker.Mock(spec=Sapphire, port=0x1337)
    server.serve_path.return_value = (SERVED_ALL, ["index.html"])
    signature = mocker.Mock()
    signature.matches.side_effect = (True, False)
    target = mocker.Mock(spec=Target, binary="fake_bin")
    target.RESULT_FAILURE = Target.RESULT_FAILURE
    target.detect_failure.return_value = Target.RESULT_FAILURE
    testcases = [mocker.Mock(spec=TestCase, env_vars=[], landing_page="index.html", optional=[])]
    with ReplayManager([], server, target, signature=signature, use_harness=False) as replay:
        assert not replay.run(testcases, repeat=3, min_results=2)
        assert replay._signature == signature
        assert report.from_path.call_count == 3
        assert replay.status.iteration == 3
        assert replay.status.results == 1
        assert replay.status.ignored == 1
        assert len(replay.reports) == 1
        assert len(replay.other_reports) == 1
        assert report_0.cleanup.call_count == 1
        assert report_1.cleanup.call_count == 0
        assert report_2.cleanup.call_count == 0
    assert signature.matches.call_count == 2

def test_replay_08(mocker, tmp_path):
    """test ReplayManager.run() - any crash"""
    report = mocker.patch("grizzly.replay.replay.Report", autospec=True)
    mocker.patch("grizzly.replay.replay.mkdtemp", autospec=True, return_value=str(tmp_path))
    report_0 = mocker.Mock(spec=Report)
    report_0.crash_info.return_value.createShortSignature.return_value = "No crash detected"
    report_1 = mocker.Mock(spec=Report, major="0123abcd", minor="01239999")
    report_1.crash_info.return_value.createShortSignature.return_value = "[@ test1]"
    report_1.crash_hash.return_value = "hash1"
    report_2 = mocker.Mock(spec=Report, major="0123abcd", minor="abcd9876")
    report_2.crash_info.return_value.createShortSignature.return_value = "[@ test2]"
    report_2.crash_hash.return_value = "hash2"
    report.from_path.side_effect = (report_0, report_1, report_2)
    server = mocker.Mock(spec=Sapphire, port=0x1337)
    server.serve_path.return_value = (SERVED_ALL, ["index.html"])
    target = mocker.Mock(spec=Target, binary="fake_bin")
    target.RESULT_FAILURE = Target.RESULT_FAILURE
    target.detect_failure.return_value = Target.RESULT_FAILURE
    testcases = [mocker.Mock(spec=TestCase, env_vars=[], landing_page="index.html", optional=[])]
    with ReplayManager([], server, target, any_crash=True, use_harness=False) as replay:
        assert replay.run(testcases, repeat=3, min_results=2)
        assert replay._signature is None
        assert report.from_path.call_count == 3
        assert replay.status.iteration == 3
        assert replay.status.results == 2
        assert replay.status.ignored == 0
        assert report_1.crash_hash.call_count == 1
        assert report_2.crash_hash.call_count == 1
        assert len(replay.reports) == 2
        assert not replay.other_reports
        assert report_0.cleanup.call_count == 1
        assert report_1.cleanup.call_count == 0
        assert report_2.cleanup.call_count == 0

def test_replay_09(mocker, tmp_path):
    """test ReplayManager.report_to_filesystem()"""
    # no reports
    ReplayManager.report_to_filesystem(str(tmp_path), [])
    assert not any(tmp_path.glob("*"))
    # with reports and tests
    (tmp_path / "report_expected").mkdir()
    expected = [
        mocker.Mock(
            spec=Report,
            path=str(tmp_path / "report_expected"),
            prefix="expected")]
    (tmp_path / "report_other1").mkdir()
    (tmp_path / "report_other2").mkdir()
    other = [
        mocker.Mock(
            spec=Report,
            path=str(tmp_path / "report_other1"),
            prefix="other1"),
        mocker.Mock(
            spec=Report,
            path=str(tmp_path / "report_other2"),
            prefix="other2")]
    test = mocker.Mock(spec=TestCase)
    path = tmp_path / "dest"
    ReplayManager.report_to_filesystem(str(path), expected, other, tests=[test])
    assert test.dump.call_count == 3  # called once per report
    assert not (tmp_path / "report_expected").is_dir()
    assert not (tmp_path / "report_other1").is_dir()
    assert not (tmp_path / "report_other2").is_dir()
    assert path.is_dir()
    assert (path / "reports").is_dir()
    assert (path / "reports" / "expected_logs").is_dir()
    assert (path / "other_reports").is_dir()
    assert (path / "other_reports" / "other1_logs").is_dir()
    assert (path / "other_reports" / "other2_logs").is_dir()
    # with reports and not tests
    (tmp_path / "report_expected").mkdir()
    expected = [
        mocker.Mock(
            spec=Report,
            path=str(tmp_path / "report_expected"),
            prefix="expected")]
    path = tmp_path / "dest2"
    ReplayManager.report_to_filesystem(str(path), expected)
    assert not (tmp_path / "report_expected").is_dir()
    assert path.is_dir()
    assert (path / "reports" / "expected_logs").is_dir()

def test_replay_10(mocker, tmp_path):
    """test ReplayManager.run() - TargetLaunchError"""
    report = mocker.patch("grizzly.replay.replay.Report", autospec=True)
    mocker.patch("grizzly.replay.replay.mkdtemp", autospec=True, return_value=str(tmp_path))
    report.from_path.side_effect = (mocker.Mock(spec=Report),)
    server = mocker.Mock(spec=Sapphire, port=0x1337)
    target = mocker.Mock(spec=Target)
    target.launch.side_effect = TargetLaunchError
    testcases = [mocker.Mock(spec=TestCase, env_vars=[], landing_page="index.html")]
    with ReplayManager([], server, target, use_harness=False) as replay:
        with raises(TargetLaunchError):
            replay.run(testcases)
        assert not any(replay.reports)
        assert any(replay.other_reports)
        assert "STARTUP" in replay._reports_other

def test_replay_11(mocker):
    """test ReplayManager.run() - multiple TestCases - no repro"""
    server = mocker.Mock(spec=Sapphire, port=0x1337)
    server.serve_path.return_value = (SERVED_ALL, ["index.html"])
    target = mocker.Mock(spec=Target)
    target.RESULT_NONE = Target.RESULT_NONE
    target.closed = True
    target.detect_failure.return_value = Target.RESULT_NONE
    target.forced_close = True
    target.rl_reset = 1
    testcases = [
        mocker.Mock(spec=TestCase, env_vars=[], landing_page="index.html", optional=[]),
        mocker.Mock(spec=TestCase, env_vars=[], landing_page="index.html", optional=[]),
        mocker.Mock(spec=TestCase, env_vars=[], landing_page="index.html", optional=[])]
    with ReplayManager([], server, target, use_harness=True) as replay:
        assert not replay.run(testcases)
        assert replay.status.ignored == 0
        assert replay.status.iteration == 1
        assert replay.status.results == 0
        assert not replay.reports
    assert all(x.dump.call_count == 1 for x in testcases)

def test_replay_12(mocker):
    """test ReplayManager.run() - multiple TestCases - successful repro"""
    server = mocker.Mock(spec=Sapphire, port=0x1337)
    server.serve_path.return_value = (SERVED_ALL, ["index.html"])
    target = mocker.Mock(spec=Target, binary="fake_bin", rl_reset=1)
    target.RESULT_FAILURE = Target.RESULT_FAILURE
    target.RESULT_NONE = Target.RESULT_NONE
    target.detect_failure.side_effect = (
        Target.RESULT_NONE,
        Target.RESULT_NONE,
        Target.RESULT_FAILURE)
    target.save_logs = _fake_save_logs_result
    testcases = [
        mocker.Mock(spec=TestCase, env_vars=[], landing_page="index.html", optional=[]),
        mocker.Mock(spec=TestCase, env_vars=[], landing_page="index.html", optional=[]),
        mocker.Mock(spec=TestCase, env_vars=[], landing_page="index.html", optional=[])]
    with ReplayManager([], server, target, use_harness=True) as replay:
        assert replay.run(testcases)
        assert replay.status.ignored == 0
        assert replay.status.iteration == 1
        assert replay.status.results == 1
        assert len(replay.reports) == 1
        assert not replay.other_reports
    assert all(x.dump.call_count == 1 for x in testcases)
