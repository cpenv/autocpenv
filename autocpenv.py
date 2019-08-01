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
from functools import partial


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
        packages = os.path.join(self.GetEventDirectory(), 'packages')
        if packages not in sys.path:
            sys.path.insert(1, packages)

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

        # First attempt
        resolver = return_first_result(
            (self.resolve_from_job_environment, (job,)),
            (self.resolve_from_job_scenefile, (job,)),
            (self.resolve_from_job_plugin, (plugin_mapping, job_plugin))
        )

        resolved_env = ' '.join([item.name for item in resolver.resolved])
        self.log('Setting Environment: {}'.format(resolved_env))

        # Combine cpenv environment with current job environment
        env = resolver.combine()
        job_env = env_to_dict(get_job_env(job))
        new_env = dict_to_env(join_dicts(job_env, env))

        # Set new job environment key values
        for k, v in new_env.items():
            self.LogInfo(': '.join([k, v]))
            job.SetJobEnvironmentKeyValue(k, v)
            RepositoryUtils.SaveJob(job)

    def resolve_from_job_environment(self, job):

        resolver = None
        py_env = job.GetJobEnvironmentKeyValue('CPENV_ACTIVE')
        modules = job.GetJobEnvironmentKeyValue('CPENV_ACTIVE_MODULES')
        env_paths = []
        if py_env:
            env_paths.append(py_env)
        if modules:
            env_paths.append(split_path(modules))
        if env_paths:
            try:
                resolver = cpenv.resolve(*env_paths)
                self.log('Resolved from job environment.')
            except ResolveError as e:
                self.log('Failed to resolve environment from autocpenv config')
                self.log(str(e))
        else:
            self.log('Job was not submitted with a CPENV environment.')

        return resolver

    def resolve_from_job_scenefile(self, job):

        resolver = None
        scene_file = job.GetJobPluginInfoKeyValue('SceneFile')
        if scene_file:
            scene_root = os.path.dirname(scene_file)
            try:
                resolver = cpenv.resolve(scene_root)
                self.log('Resolved environment for ' + scene_root)
            except ResolveError as e:
                self.log('Failed to auto-resolve for ' + scene_root)
                self.log(str(e))

        return resolver

    def resolve_from_job_plugin(self, plugin_mapping, job_plugin):

        resolver = None
        plugin_mapping = plugin_mapping_to_dict(plugin_mapping)
        env_paths = plugin_mapping.get(job_plugin, None)

        if not env_paths:
            self.log('No plugin mapping for: {}'.format(job_plugin))
            return

        # Resolve cpenv environment and module
        try:
            resolver = cpenv.resolve(*env_paths)
            self.log('Resolved environment using autocpenv config.')
        except ResolveError as e:
            self.log('Failed to resolve environment from autocpenv config')
            self.log(str(e))

        return resolver

    def log(self, message):
        '''prepends AUTOCPENV: to logging messages'''

        self.LogInfo('AUTOCPENV: {}'.format(message))


def return_first_result(*funcs):
    for func, args in funcs:
        result = func(*args)
        if result:
            return result


def get_job_env(job):
    '''Get a jobs environment as a dictionary'''

    env = {}
    for k in job.GetJobEnvironmentKeys():
        env[k] = job.GetJobEnvironmentKeyValue(k)
    return env


def split_path(path, pathsep=os.pathsep):
    if pathsep in path:
        return path.split(pathsep)
    return path


def plugin_mapping_to_dict(plugin_mapping):
    '''Convert the plugin_mapping config entry to a dictionary'''

    d = {}

    for line in plugin_mapping.split(';'):
        plugin, env_paths = line.split('=')
        d.setdefault(plugin, env_paths.split())

    return d
