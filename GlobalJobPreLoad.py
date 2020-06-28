# -*- coding: utf-8 -*-
import os
import sys

from System.IO import *
from Deadline.Scripting import *


def __main__(deadlinePlugin):
    job = deadlinePlugin.GetJob()

    # Get job cpenv requirements
    requirements = job.SetJobEnvironmentKeyValue('CPENV_ACTIVE_MODULES')
    if not requirements:
        job.LogInfo('Job has no cpenv requirements...')
        return

    # Import cpenv
    autocpenv = RepositoryUtils.GetEventPluginDirectory("autocpenv")
    packages = os.path.join(autocpenv, 'packages')
    if packages not in sys.path:
        sys.path.insert(1, packages)

    import cpenv

