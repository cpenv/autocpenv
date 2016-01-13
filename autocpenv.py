from System.Diagnostics import *
from System.IO import *
from System import TimeSpan

from Deadline.Events import *
from Deadline.Scripting import *
from Deadline.Slaves import *

import sys
import os
import textwrap


def GetDeadlineEventListener():
    return AutoCpenv()


def CleanupDeadlineEventListener(eventListener):
    eventListener.Cleanup()


class AutoCpenv(DeadlineEventListener):
    '''
    Listen for OnSlaveRendering events then activate the configured cpenv
    environments and modules.
    '''

    def __init__(self):
        self.OnSlaveRenderingCallback += self.OnSlaveRendering

    def Cleanup(self):
        del self.OnSlaveRenderingCallback

    def configure(self):
        sys.path.insert(1, os.path.join(self.GetEventDirectory(), 'packages'))

    def OnSlaveRendering(self, slave_name, job):

        self.configure()
        from cpenv.api import (VirtualEnvironment, ApplicationModule,
                               get_home_environment)

        environment = self.GetConfigEntry('Environment')
        if not environment:
            ClientUtils.LogText('No environment specified...')
            return

        module_mapping_str = self.GetConfigEntry('ModuleMapping')
        if not module_mapping_str:
            log('No module mapping specified...')
            return

        job_plugin = job.JobPlugin
        module_mapping = module_mapping_to_dict(module_mapping_str)

        if job_plugin in module_mapping:
            if os.path.exists(environment):
                env = VirtualEnvironment(environment)
            else:
                env = get_home_environment(environment)
            log('Activating ' + env.name)
            env.activate()

            modules = module_mapping[job_plugin]
            for mod in modules:
                module = env.get_application_module(mod)
                log('including module ' + module.name)
                module.activate()

            for k, v in os.environ.items():
                job.SetJobEnvironmentKeyValue(k, v)


def log(msg):
    msg = textwrap.fill(
        'AUTOCPENV: {}'.format(msg),
        initial_indent='',
        subsequent_indent='    '
    )
    ClientUtils.LogText(msg)


def module_mapping_to_dict(module_mapping):

    d = {}

    for line in module_mapping.split(';'):
        plugin, modules = line.split('=')
        modules = modules.split()
        d.setdefault(plugin, modules)

    return d
