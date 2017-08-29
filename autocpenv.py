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
    Listen for OnSlaveStartingJob events then activate the configured cpenv
    environment and modules.
    '''

    def __init__(self):
        self.OnJobSubmittedCallback += self.OnJobSubmitted

    def Cleanup(self):
        del self.OnJobSubmittedCallback

    def configure_cpenv(self):
        '''Configure cpenv python package'''

        cpenv_home = self.GetConfigEntry('cpenv_home')
        if not cpenv_home:
            self.log('Missing required field: CPENV_HOME')
            return False

        os.environ['CPENV_HOME'] = cpenv_home
        sys.path.insert(1, os.path.join(self.GetEventDirectory(), 'packages'))

        try:
            import cpenv
        except ImportError:
            return False

        return True

    def OnJobSubmitted(self, job):
        plugin_mapping = self.GetConfigEntry('plugin_mapping')
        logging = self.GetConfigEntry('logging')

        if not plugin_mapping:
            self.log('Missing required field: Plugin Mapping')
            return

        success = self.configure_cpenv()
        if not success:
            self.log('Failed to configure cpenv...')
            return

        import cpenv
        from cpenv.utils import env_to_dict, join_dicts, dict_to_env
        from cpenv.resolver import ResolveError

        job_plugin = job.JobPlugin
        resolved = False

        # Attempt to resolve the environment using the scenes root path
        scene_file = job.GetJobPluginInfoKeyValue('SceneFile')
        if scene_file:
            scene_root = os.path.dirname(scene_file)
            try:
                r = cpenv.resolve(scene_root)
                self.log('Resolved environment for ' + scene_root)
                resolved = True
            except ResolveError as e:
                self.log('Failed to auto-resolve for ' + scene_root)
                self.log(str(e))
                resolved = False

        # If env not resolved, fall back to autocpenv plugin_mapping
        if not resolved:
            plugin_mapping = plugin_mapping_to_dict(plugin_mapping)
            env_paths = plugin_mapping.get(job_plugin, None)

            if not env_paths:
                self.log('No plugin mapping for: {}'.format(job_plugin))
                return

            # Resolve cpenv environment and module
            try:
                r = cpenv.resolve(*env_paths)
                resolved = True
            except ResolveError as e:
                self.log('Failed to resolve environment from autocpenv config')
                self.log(str(e))
                resolved = False

        if not resolved:
            return

        resolved_env = ' '.join([item.name for item in r.resolved])
        self.log('Setting Environment: {}'.format(resolved_env))

        # Combine cpenv environment with current job environment
        env = r.combine()
        job_env = env_to_dict(get_job_env(job))
        new_env = dict_to_env(join_dicts(job_env, env))

        # Set new job environment key values
        for k, v in new_env.items():
            self.LogInfo(': '.join([k, v]))
            job.SetJobEnvironmentKeyValue(k, v)
            RepositoryUtils.SaveJob(job)

    def log(self, message):
        '''Log Info method prepends AUTOCPENV: to logging messages'''

        self.LogInfo('AUTOCPENV: {}'.format(message))


def get_job_env(job):
    '''Get a jobs environment as a dictionary'''

    env = {}
    for k in job.GetJobEnvironmentKeys():
        env[k] = job.GetJobEnvironmentKeyValue(k)
    return env


def plugin_mapping_to_dict(plugin_mapping):
    '''Convert the plugin_mapping config entry to a dictionary'''

    d = {}

    for line in plugin_mapping.split(';'):
        plugin, env_paths = line.split('=')
        d.setdefault(plugin, env_paths.split())

    return d
