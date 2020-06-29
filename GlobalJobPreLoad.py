# -*- coding: utf-8 -*-
import sys

from System.IO import *
from Deadline.Scripting import *


def __main__(plugin):

    # Execute autocpenv GlobalJobPreLoad
    autocpenv = RepositoryUtils.GetEventPluginDirectory('autocpenv')
    if autocpenv not in sys.path:
        sys.path.insert(1, autocpenv)

    import autocpenv
    autocpenv.GlobalJobPreLoad(plugin)
