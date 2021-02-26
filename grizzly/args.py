# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from argparse import ArgumentParser, HelpFormatter
from logging import CRITICAL, DEBUG, ERROR, INFO, WARNING
from os import listdir
from os.path import exists, isfile, isdir

from .adapters import names as adapter_names
from .common.utils import TIMEOUT_DELAY
from .target import available as available_targets

# ref: https://stackoverflow.com/questions/12268602/sort-argparse-help-alphabetically
class SortingHelpFormatter(HelpFormatter):
    @staticmethod
    def __sort_key(action):
        for opt in action.option_strings:
            if opt.startswith("--"):
                return [opt]
        return action.option_strings

    def add_usage(self, usage, actions, groups, prefix=None):
        actions = sorted(actions, key=self.__sort_key)
        super().add_usage(usage, actions, groups, prefix)

    def add_arguments(self, actions):
        actions = sorted(actions, key=self.__sort_key)
        super().add_arguments(actions)


class CommonArgs:
    IGNORABLE = ("log-limit", "memory", "timeout")
    IGNORE = ("log-limit", "timeout")

    def __init__(self):
        super().__init__()
        # log levels for console logging
        self._level_map = {
            "CRIT": CRITICAL,
            "ERROR": ERROR,
            "WARN": WARNING,
            "INFO": INFO,
            "DEBUG": DEBUG}
        self._sanity_skip = set()

        if not hasattr(self, "parser"):
            self.parser = ArgumentParser(
                formatter_class=SortingHelpFormatter,
                conflict_handler='resolve')

        self.parser.add_argument(
            "binary",
            help="Firefox binary to run")
        self.parser.add_argument(
            "--log-level", default="INFO",
            help="Configure console logging. Options: %s (default: %%(default)s)" %
            ", ".join(k for k, v in sorted(self._level_map.items(), key=lambda x: x[1])))

        self.launcher_grp = self.parser.add_argument_group("Launcher Arguments")
        self.launcher_grp.add_argument(
            "-e", "--extension", action="append",
            help="Install an extension. Specify the path to the xpi or the directory"
                 " containing the unpacked extension. To install multiple extensions"
                 " specify multiple times")
        self.launcher_grp.add_argument(
            "--launch-timeout", type=int, default=300,
            help="Number of seconds to wait before LaunchError is raised (default: %(default)s)")
        self.launcher_grp.add_argument(
            "--log-limit", type=int, default=0,
            help="Browser log file size limit in MBs (default: 'no limit')")
        self.launcher_grp.add_argument(
            "-m", "--memory", type=int, default=0,
            help="Browser process memory limit in MBs (default: 'no limit')")
        self.launcher_grp.add_argument(
            "--platform", default="ffpuppet",
            help="Platforms available: %s (default: %%(default)s)" % ", ".join(available_targets()))
        self.launcher_grp.add_argument(
            "-p", "--prefs",
            help="prefs.js file to use")
        self.launcher_grp.add_argument(
            "--relaunch", type=int, default=1000,
            help="Number of iterations performed before relaunching the browser (default: %(default)s)")
        self.launcher_grp.add_argument(
            "--time-limit", type=int, default=None,
            help="This is the maximum amount of time that a test is expected to take."
                 " After the time has elapsed the harness will attempt to close the test."
                 " By default `Adapter.TIME_LIMIT` is used."
                 " Browser build types and debuggers can affect the amount of time"
                 " required to run a test case.")
        self.launcher_grp.add_argument(
            "-t", "--timeout", type=int, default=None,
            help="Iteration timeout in seconds. By default this is `test-duration`+%ds."
                 " If the timeout is reached the target is assumed to be in a bad state"
                 " and will be closed. Typically this should be a few seconds greater"
                 " than the value used for `test-duration`." % (TIMEOUT_DELAY,))
        self.launcher_grp.add_argument(
            "--valgrind", action="store_true",
            help="Use Valgrind (Linux only)")
        self.launcher_grp.add_argument(
            "--xvfb", action="store_true",
            help="Use Xvfb (Linux only)")

        self.reporter_grp = self.parser.add_argument_group("Reporter Arguments")
        self.reporter_grp.add_argument(
            "--fuzzmanager", action="store_true",
            help="Report results to FuzzManager")
        self.reporter_grp.add_argument(
            "--ignore", nargs="*", default=list(self.IGNORE),
            help="Space separated list of issue types to ignore. Valid options: %s"
                 " (default: %s)" % (" ".join(self.IGNORABLE), " ".join(self.IGNORE)))
        self.reporter_grp.add_argument(
            "--tool",
            help="Override tool name used when reporting issues to FuzzManager")

        self.parser.epilog = "For addition help check out the wiki:" \
            " https://github.com/MozillaSecurity/grizzly/wiki"

    def parse_args(self, argv=None):
        args = self.parser.parse_args(argv)
        self.sanity_check(args)
        return args

    def sanity_check(self, args):
        if hasattr(super(), 'sanity_check'):
            super().sanity_check(args)

        if "binary" not in self._sanity_skip and not isfile(args.binary):
            self.parser.error("file not found: %r" % args.binary)

        # sanitize ignore list
        args.ignore = {arg.lower() for arg in args.ignore}
        for ignore in args.ignore:
            if ignore not in self.IGNORABLE:
                self.parser.error("Unrecognized ignore value: %s" % ignore)

        if "input" not in self._sanity_skip and args.input:
            if not exists(args.input):
                self.parser.error("%r does not exist" % args.input)
            elif isdir(args.input) and not listdir(args.input):
                self.parser.error("%r is empty" % args.input)

        # check log level
        log_level = self._level_map.get(args.log_level.upper(), None)
        if log_level is None:
            self.parser.error("Invalid log-level %r" % args.log_level)
        args.log_level = log_level

        if args.log_limit < 0:
            self.parser.error("--log-limit must be >= 0")
        args.log_limit *= 1048576

        if args.memory < 0:
            self.parser.error("-m/--memory must be >= 0")
        args.memory *= 1048576

        if args.relaunch < 1:
            self.parser.error("--relaunch must be >= 1")

        if args.extension:
            for ext in args.extension:
                if not exists(ext):
                    self.parser.error("%r does not exist" % ext)
                if not isdir(ext) or (isfile(ext) and ext.endswith(".xpi")):
                    self.parser.error("Extension must be a folder or .xpi")

        if args.platform.lower() not in set(available_targets()):
            self.parser.error("Unsupported platform %r" % args.platform)

        if args.prefs and not isfile(args.prefs):
            self.parser.error("-p/--prefs not found %r" % args.prefs)

        if args.time_limit is not None and args.time_limit < 1:
            self.parser.error("--time-limit must be at least 1")

        if args.timeout is not None and args.timeout < 1:
            self.parser.error("--timeout must be at least 1")

        if "tool" not in self._sanity_skip:
            if args.tool is not None and not args.fuzzmanager:
                self.parser.error("--tool can only be given with --fuzzmanager")


class GrizzlyArgs(CommonArgs):
    def __init__(self):
        super().__init__()
        self._adapters = sorted(adapter_names())
        self._sanity_skip.add("tool")
        self.parser.add_argument(
            "adapter",
            help="Available adapters: %s" % ", ".join(self._adapters))
        self.parser.add_argument(
            "--enable-profiling", action="store_true",
            help="Record profiling data. The data can be viewed by running the"
                 " status reporter while running Grizzly.")
        self.parser.add_argument(
            "-i", "--input",
            help="Test case or directory containing test cases")
        self.parser.add_argument(
            "--limit", type=int, default=0,
            help="Maximum number of iterations to be performed. (default: no limit)")
        self.parser.add_argument(
            "-v", "--verbose", action="store_true",
            help="Output console updates every iteration. By default the number"
                 " of iterations between console updates doubles each update."
                 " Updates are always printed when a result is detected or the"
                 " target is relaunched.")

        self.launcher_grp.add_argument(
            "--coverage", action="store_true",
            help="Enable coverage collection")
        self.launcher_grp.add_argument(
            "--rr", action="store_true",
            help="Use RR (Linux only)")

        self.reporter_grp.add_argument(
            "-c", "--collect", type=int, default=1,
            help="Maximum number of test cases to include in the report (default: %(default)s)")
        self.reporter_grp.add_argument(
            "--s3-fuzzmanager", action="store_true",
            help="Report large attachments (if any) to S3 and then the crash & S3 link to FuzzManager")

    def sanity_check(self, args):
        super().sanity_check(args)

        if args.adapter.lower() not in self._adapters:
            msg = ["Adapter %r does not exist." % args.adapter.lower()]
            if self._adapters:
                msg.append("Available adapters: %s" % ", ".join(self._adapters))
            else:
                msg.append("No adapters available.")
            self.parser.error(" ".join(msg))

        if args.collect < 1:
            self.parser.error("--collect must be greater than 0")

        if args.fuzzmanager and args.s3_fuzzmanager:
            self.parser.error("--fuzzmanager and --s3-fuzzmanager are mutually exclusive")

        if args.limit < 0:
            self.parser.error("--limit must be >= 0 (0 = no limit)")

        if args.tool is not None and not (args.fuzzmanager or args.s3_fuzzmanager):
            self.parser.error("--tool can only be given with --fuzzmanager/--s3-fuzzmanager")

        if args.rr and args.valgrind:
            self.parser.error("'--rr' and '--valgrind' cannot be used together")
