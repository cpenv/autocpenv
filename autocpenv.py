from System.Diagnostics import *
from System.IO import *
from System import TimeSpan

from Deadline.Events import *
from Deadline.Scripting import *
from Deadline.Slaves import *

import sys
import os
import pprint
import textwrap


def GetDeadlineEventListener():
    return AutoCpenv()


def CleanupDeadlineEventListener(eventListener):
    eventListener.Cleanup()


class AutoCpenv(DeadlineEventListener):
    '''
    Listen for OnJobStarted events then activate the configured cpenv
    environments and modules.
    '''

    def __init__(self):
        self.OnJobStartedCallback += self.OnJobStarted

    def Cleanup(self):
        del self.OnJobStartedCallback

    def configure(self):
        sys.path.insert(1, os.path.join(self.GetEventDirectory(), 'packages'))

    def OnJobStarted(self, job):

        self.configure()
        import cpenv
        from cpenv.utils import env_to_dict, join_dicts, dict_to_env

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
        module = module_mapping.get(job_plugin, None)[0]

        if module:
            log('Setting Environment: {}, {}'.format(environment, module))

            # Resolve cpenv environment and module
            r = cpenv.resolve(environment, module)

            # Combine cpenv environment with current job environment
            env = r.combine()
            job_env = env_to_dict(get_job_env(job))
            new_env = dict_to_env(join_dicts(job_env, env))

            # Set new job environment key values
            for k, v in new_env.items():
                log(': '.join([k, v]))
                job.SetJobEnvironmentKeyValue(k, v)


def get_job_env(job):
    env = {}
    for k in job.GetJobEnvironmentKeys():
        env[k] = job.GetJobEnvironmentKeyValue(k)
    return env

def log(msg):
    ClientUtils.LogText('AUTOCPENV: {}'.format(msg))


def module_mapping_to_dict(module_mapping):

    d = {}

    for line in module_mapping.split(';'):
        plugin, modules = line.split('=')
        modules = modules.split()
        d.setdefault(plugin, modules)

    return d
