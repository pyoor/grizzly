# pylint: disable=protected-access
from os import listdir
from os.path import isdir
from shutil import rmtree

from pytest import mark, raises

from .adb_process import ADBLaunchError, ADBProcess
from .adb_session import ADBSession, ADBSessionError


def test_adb_process_01(mocker):
    """test creating a simple device"""
    test_pkg = "org.test.preinstalled"
    fake_session = mocker.Mock(
        spec_set=ADBSession, SANITIZER_LOG_PREFIX="/fake/log.txt"
    )
    with ADBProcess(test_pkg, fake_session) as proc:
        assert isinstance(proc._session, ADBSession)
        assert proc._package == test_pkg
        assert proc.logs is None
        assert proc.profile is None
        assert proc.reason == proc.RC_CLOSED
        assert proc._pid is None
        proc.close()
        assert not proc.logs  # should not have logs


def test_adb_process_02(mocker):
    """test creating device with unknown package"""
    fake_session = mocker.Mock(spec_set=ADBSession)
    fake_session.is_installed.return_value = False
    with raises(ADBSessionError, match="Package 'org.test.unknown' is not installed"):
        ADBProcess("org.test.unknown", fake_session)


def test_adb_process_03(mocker):
    """test ADBProcess.launch() unsupported app"""
    fake_session = mocker.Mock(spec_set=ADBSession)
    fake_session.SANITIZER_LOG_PREFIX = "/fake/log/prefix.txt"
    with ADBProcess("org.some.app", fake_session) as proc:
        with raises(ADBLaunchError, match="Unsupported package 'org.some.app'"):
            proc.launch("fake.url")


def test_adb_process_04(mocker):
    """test ADBProcess.launch() failed bootstrap setup"""
    mocker.patch("grizzly.target.adb_device.adb_process.Bootstrapper", autospec=True)
    mocker.patch("grizzly.target.adb_device.adb_process.sleep", autospec=True)
    fake_session = mocker.Mock(spec_set=ADBSession)
    fake_session.SANITIZER_LOG_PREFIX = "/fake/log/prefix.txt"
    fake_session.collect_logs.return_value = b""
    fake_session.listdir.return_value = ()
    fake_session.get_pid.return_value = None
    fake_session.reverse.return_value = False
    with ADBProcess("org.mozilla.fenix", fake_session) as proc:
        with raises(ADBLaunchError, match="Could not reverse port"):
            proc.launch("fake.url")


def test_adb_process_05(mocker):
    """test ADBProcess.launch() package is running (bad state)"""
    fake_session = mocker.Mock(spec_set=ADBSession)
    fake_session.SANITIZER_LOG_PREFIX = "/fake/log/prefix.txt"
    fake_session.call.return_value = (1, "")
    fake_session.collect_logs.return_value = b""
    fake_session.listdir.return_value = ()
    fake_session.process_exists.return_value = False
    with ADBProcess("org.mozilla.fenix", fake_session) as proc:
        with raises(ADBLaunchError, match="'org.mozilla.fenix' is already running"):
            proc.launch("fake.url")
        assert not proc.is_running()
        proc.cleanup()
        assert proc.logs is None


# TODO: check config yaml output
# def test_adb_process_06(mocker, tmp_path):
#    """test ADBProcess.launch() check *-geckoview-config.yaml"""


def test_adb_process_07(mocker):
    """test ADBProcess.launch(), ADBProcess.is_running() and ADBProcess.is_healthy()"""
    fake_bs = mocker.patch(
        "grizzly.target.adb_device.adb_process.Bootstrapper", autospec=True
    )
    fake_bs.return_value.location.return_value = "http://localhost"
    fake_bs.return_value.port.return_value = 1234
    fake_session = mocker.Mock(spec_set=ADBSession)
    fake_session.SANITIZER_LOG_PREFIX = "/fake/log/prefix.txt"
    fake_session.call.return_value = (0, "Status: ok")
    fake_session.collect_logs.return_value = b""
    fake_session.get_pid.side_effect = (None, 1337)
    fake_session.listdir.return_value = ()
    # fake_session.process_exists.return_value = False
    with ADBProcess("org.mozilla.geckoview_example", fake_session) as proc:
        assert not proc.is_running()
        assert proc.launches == 0
        assert proc.launch("fake.url")
        assert proc.is_running()
        assert proc.is_healthy()
        assert proc.launches == 1
        proc.close()
        assert proc._pid is None
        assert proc.logs
    assert fake_bs.return_value.wait.call_count == 1
    assert fake_bs.return_value.close.call_count == 1


def test_adb_process_08(mocker):
    """test ADBProcess.launch() with environment variables"""
    fake_bs = mocker.patch(
        "grizzly.target.adb_device.adb_process.Bootstrapper", autospec=True
    )
    fake_bs.return_value.location.return_value = "http://localhost"
    fake_bs.return_value.port.return_value = 1234
    fake_session = mocker.Mock(spec_set=ADBSession)
    fake_session.SANITIZER_LOG_PREFIX = "/fake/log/prefix.txt"
    fake_session.call.return_value = (0, "Status: ok")
    fake_session.collect_logs.return_value = b""
    fake_session.get_pid.side_effect = (None, 1337)
    fake_session.listdir.return_value = ()
    env = {"test1": "1", "test2": "2"}
    with ADBProcess("org.mozilla.geckoview_example", fake_session) as proc:
        assert proc.launch("fake.url", env_mod=env)
        assert proc.is_running()
        proc.close()


def test_adb_process_09(mocker):
    """test ADBProcess.wait_on_files()"""
    mocker.patch("grizzly.target.adb_device.adb_process.Bootstrapper", autospec=True)
    fake_session = mocker.Mock(spec_set=ADBSession)
    fake_session.SANITIZER_LOG_PREFIX = "/fake/log/prefix.txt"
    fake_session.call.return_value = (0, "Status: ok")
    fake_session.collect_logs.return_value = b""
    fake_session.get_pid.side_effect = (None, 1337)
    fake_session.open_files.return_value = ((1, "some_file"),)
    fake_session.listdir.return_value = ()
    fake_session.realpath.side_effect = str.strip
    with ADBProcess("org.mozilla.geckoview_example", fake_session) as proc:
        proc.wait_on_files(["not_running"])
        assert proc.launch("fake.url")
        assert proc.wait_on_files([])
        mocker.patch("grizzly.target.adb_device.adb_process.sleep", autospec=True)
        mocker.patch(
            "grizzly.target.adb_device.adb_process.time", side_effect=(1, 1, 2)
        )
        fake_session.open_files.return_value = (
            (1, "some_file"),
            (1, "/existing/file.txt"),
        )
        assert not proc.wait_on_files(
            ["/existing/file.txt"], poll_rate=0.1, timeout=0.3
        )
        proc.close()


def test_adb_process_10(mocker):
    """test ADBProcess.find_crashreports()"""
    mocker.patch("grizzly.target.adb_device.adb_process.Bootstrapper", autospec=True)
    fake_session = mocker.Mock(spec_set=ADBSession)
    fake_session.SANITIZER_LOG_PREFIX = "/fake/log/prefix.txt"
    with ADBProcess("org.some.app", fake_session) as proc:
        proc.profile = "profile_path"
        # no log or minidump files
        fake_session.listdir.return_value = []
        assert not proc.find_crashreports()
        # sanitizer logs
        fake_session.listdir.side_effect = (["asan.log"], AssertionError())
        assert any(x.endswith("asan.log") for x in proc.find_crashreports())
        # contains minidump file
        fake_session.listdir.side_effect = ([], ["somefile.txt", "test.dmp"])
        assert any(x.endswith("test.dmp") for x in proc.find_crashreports())
        # contains missing path
        fake_session.listdir.side_effect = ([], IOError("test"))
        assert not proc.find_crashreports()


def test_adb_process_11(mocker, tmp_path):
    """test ADBProcess.save_logs()"""
    mocker.patch("grizzly.target.adb_device.adb_process.Bootstrapper", autospec=True)
    fake_session = mocker.Mock(spec_set=ADBSession)
    fake_session.SANITIZER_LOG_PREFIX = "/fake/log/prefix.txt"
    log_path = tmp_path / "src"
    log_path.mkdir()
    (log_path / "nested").mkdir()
    fake_log = log_path / "fake.txt"
    fake_log.touch()
    dmp_path = tmp_path / "dst"
    with ADBProcess("org.some.app", fake_session) as proc:
        # without proc.logs set
        proc.save_logs(str(dmp_path))
        # with proc.logs set
        proc.logs = str(log_path)
        proc.save_logs(str(dmp_path))
    assert any(dmp_path.glob("fake.txt"))


def test_adb_process_12(mocker):
    """test ADBProcess._process_logs()"""
    mocker.patch("grizzly.target.adb_device.adb_process.Bootstrapper", autospec=True)
    mocker.patch("grizzly.target.adb_device.adb_process.PuppetLogger", autospec=True)
    fake_proc_md = mocker.patch(
        "grizzly.target.adb_device.adb_process.process_minidumps", autospec=True
    )
    fake_session = mocker.Mock(spec_set=ADBSession)
    fake_session.SANITIZER_LOG_PREFIX = "/fake/log/prefix.txt"
    fake_session.collect_logs.return_value = b"fake logcat data"
    with ADBProcess("org.some.app", fake_session) as proc:
        # no extra logs
        proc._process_logs([])
        assert isdir(proc.logs)
        try:
            assert "log_logcat.txt" in listdir(proc.logs)
        finally:
            rmtree(proc.logs)
        proc.logs = None
        assert fake_proc_md.call_count == 0
        assert fake_session.pull.call_count == 0
        # other logs available
        proc._process_logs(["log.dmp", "asan_log.txt"])
        assert isdir(proc.logs)
        try:
            assert "log_logcat.txt" in listdir(proc.logs)
        finally:
            rmtree(proc.logs)
        assert fake_proc_md.call_count == 1
        assert fake_session.pull.call_count == 2


def test_adb_process_13(tmp_path):
    """test ADBProcess._split_logcat()"""
    log_path = tmp_path / "logs"
    log_path.mkdir()
    # missing log_logcat.txt
    ADBProcess._split_logcat(str(log_path), "fake.package")
    assert not any(log_path.iterdir())
    # with log_logcat.txt
    (tmp_path / "logs" / "log_logcat.txt").write_text(
        "07-27 12:10:15.414  80  80 W art     :"
        " Unexpected CPU variant for X86 using defaults: x86\n"
        "07-27 12:10:15.430  90  90 I GeckoApplication:"
        " zerdatime 3349725 - application start\n"
        "07-27 12:10:15.442  90  44 I GeckoThread: preparing to run Gecko\n"
        "07-27 12:10:15.442  90  44 E GeckoLibLoad: Load sqlite start\n"
        "07-27 12:10:15.496  81  81 I GRALLOC-DRM: foo\n"
        "07-27 12:10:15.505  90  43 I GeckoDump: test, line1\n"
        "07-27 12:10:15.505  90  43 E GeckoApp: test, line2\n"
        "07-27 12:10:15.520  82  49 I EGL-DRI2: found extension DRI_Core version 1\n"
        "07-27 12:10:15.521  82  49 I OpenGLRenderer: Initialized EGL, version 1.4\n"
        "07-27 12:10:15.528  90  44 E GeckoLibLoad: Load sqlite done\n"
        "07-27 12:10:15.529  80  80 W art     : Suspending all threads took: 8.966ms\n"
        "07-27 12:10:15.533  90  44 E GeckoLibLoad: Load nss done\n"
        "07-27 12:39:27.188  39  39 W Fake  : asdf\n"
        "07-27 12:39:27.239  17  14 I InputReader:"
        " Reconfiguring input devices.  changes=0x00000010\n"
        "07-27 12:39:27.440  78  78 E android.os.Debug:"
        " failed to load memtrack module: 90\n"
        "07-27 12:39:27.441  78  78 I Radio-JNI: register_android_hardware_Radio DONE\n"
        "07-27 12:39:27.442 18461 18481 F MOZ_CRASH: Hit MOZ_CRASH(test) at gpp.rs:17\n"
        "07-27 12:39:27.443  90  90 I eckoThrea: potentially missed\n"
    )
    ADBProcess._split_logcat(str(log_path), "fake.package")
    assert any(log_path.iterdir())
    assert (tmp_path / "logs" / "log_stdout.txt").read_text().rstrip() == "test, line1"
    stderr_lines = (tmp_path / "logs" / "log_stderr.txt").read_text().splitlines()
    assert "test, line2" in stderr_lines
    assert "test, line1" not in stderr_lines
    assert len(stderr_lines) == 8


@mark.parametrize(
    "input_data, result",
    [
        ("", dict()),
        ('junk\n#user_pref("a.b", 0)\n', dict()),
        ('user_pref("a.b.c", false);\n', {"a.b.c": False}),
        ('user_pref("a.b.c", 0);', {"a.b.c": 0}),
        ("user_pref(\"a.b.c\", 'test');", {"a.b.c": "test"}),
        ('user_pref("a.b.c", "test");', {"a.b.c": "test"}),
        ('user_pref("a.b", 1);\nuser_pref("a.c", true);', {"a.b": 1, "a.c": True}),
        ('user_pref("a.b", 1);\n#\nuser_pref("a.c", 1);', {"a.b": 1, "a.c": 1}),
    ],
)
def test_adb_process_14(tmp_path, input_data, result):
    """test ADBProcess.prefs_to_dict()"""
    prefs_js = tmp_path / "prefs.js"
    prefs_js.write_text(input_data)
    assert ADBProcess.prefs_to_dict(str(prefs_js)) == result
