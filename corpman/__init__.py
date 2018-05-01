# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from .corpman import CorpusManager, InputFile, TestCase, TestFile
from .loader import Loader

__all__ = ("CorpusManager", "InputFile", "loader", "TestCase", "TestFile")
__author__ = "Jesse Schwartzentruber"
__credits__ = ["Jesse Schwartzentruber"]

loader = Loader()
