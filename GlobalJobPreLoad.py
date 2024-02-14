# -*- coding: utf-8 -*-
import sys

from Deadline.Scripting import RepositoryUtils
from System.IO import *


def __main__(plugin):
    # Execute autocpenv GlobalJobPreLoad
    autocpenv = RepositoryUtils.GetEventPluginDirectory("autocpenv")
    if autocpenv not in sys.path:
        sys.path.insert(1, autocpenv)

    import autocpenv

    autocpenv.GlobalJobPreLoad(plugin)
