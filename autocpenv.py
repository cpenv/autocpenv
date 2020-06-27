# -*- coding: utf-8 -*-
# Standard library imports
import sys
import os
import traceback
from contextlib import contextmanager

# IronPython imports
from System.Diagnostics import *
from System.IO import *
from System import TimeSpan

# Deadline imports
from Deadline.Events import *
from Deadline.Scripting import *
from Deadline.Slaves import *


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
        self.OnSlaveStartingJobCallback += self.OnSlaveStartingJob
        self._log_prefix = ''

    def Cleanup(self):
        del self.OnJobSubmittedCallback
        del self.OnSlaveStartingJobCallback

    def log(self, message):
        '''Wraps LogInfo to add a prefix to all log messages.'''

        self.LogInfo('{}{}'.format(self._log_prefix, message))

    @contextmanager
    def log_section(self, header, prefix):
        '''A context manager that logs a message and sets a log prefix.'''

        self.log(header)
        old_log_prefix = self._log_prefix
        self._log_prefix = prefix
        try:
            yield
        finally:
            self._log_prefix = old_log_prefix

    def OnSlaveStartingJob(self, string, job):
        '''
        Responsible for localizing modules for each worker when a Job is
        picked up. If all workers are sharing a home location and local
        repository, this method will not localize an modules.
        '''

        success = self._load_cpenv()
        if not success:
            self.log('Failed to load cpenv...')
            return

        import cpenv

        resolved = self.resolve_from_job_environment(job)
        if not resolved:
            return

        localizer = cpenv.Localizer(cpenv.get_repo('home'))
        localizer.localize(resolved, overwrite=False)

        self.log('Success!')

    def OnJobSubmitted(self, job):
        logging = self.GetConfigEntry('logging')

        job_plugin = job.JobPlugin
        plugin_mapping = self.GetConfigEntry('plugin_mapping')
        if not plugin_mapping:
            self.log('Missing required field: Plugin Mapping')
            return

        success = self._load_cpenv()
        if not success:
            self.log('Failed to load cpenv...')
            return

        import cpenv
        from cpenv import mappings

        with self.log_section('Attempting to resolve modules...', '  '):
            resolved = return_first_result(
                (self.resolve_from_job_environment, (job,)),
                (self.resolve_from_job_scenefile, (job,)),
                (self.resolve_from_job_plugin, (plugin_mapping, job_plugin)),
            )

        if not resolved:
            self.log('Error! Failed 3 attempts to resolve modules...')
            return
        else:
            self.log('Ok! Resolved {} modules.'.format(len(resolved)))

        with self.log_section('Building job environment...', '  '):
            localizer = cpenv.Localizer(cpenv.get_repo('home'))
            localized = localizer.localize(resolved, overwrite=False)

            self.log('- Combining module environment')
            activator = cpenv.Activator(localized)
            env = activator.combine_modules(localized)

            # Combine cpenv environment with current job environment
            job_env = mappings.env_to_dict(get_job_env(job))
            new_job_env = mappings.dict_to_env(mappings.join_dicts(
                job_env,
                env,
            ))

            self.log('- Setting job environment variables')
            for k, v in new_job_env.items():
                self.log('  {}: {}'.format(k, v))
                job.SetJobEnvironmentKeyValue(k, v)

            self.log('- Saving Job')
            RepositoryUtils.SaveJob(job)

        self.log('Success!')

    def _load_cpenv(self):
        '''Configure cpenv python package'''

        cpenv_home = self.GetConfigEntry('cpenv_home')
        if cpenv_home:
            os.environ['CPENV_HOME'] = cpenv_home

        packages = os.path.join(self.GetEventDirectory(), 'packages')
        if packages not in sys.path:
            sys.path.insert(1, packages)

        try:

            import cpenv

            class _EventLogReporter(EventLogReporter, cpenv.Reporter):
                '''Inject log method and mix with cpenv.Reporter baseclass.'''
                log = self.log

            cpenv.set_reporter(_EventLogReporter)

        except ImportError:
            self.log('Failed to import cpenv...')
            self.log(traceback.format_exc())
            return False

        return True

    def resolve_from_job_environment(self, job):
        '''Attempt to resolve modules from CPENV_ACTIVE_MODULES variable.'''

        import cpenv
        self.log('Checking job environment for module requirements...')

        requirements = job.GetJobEnvironmentKeyValue('CPENV_ACTIVE_MODULES')
        if not requirements:
            self.log('  CPENV_ACTIVE_MODULES not set...')
            return

        requirements = split_path(requirements)
        try:
            resolved = cpenv.resolve(requirements)
            return resolved
        except cpenv.ResolveError:
            pass

    def resolve_from_job_scenefile(self, job):
        '''Attempt to resolve modules from the jobs scene_file.

        Walks up the path until a .cpenv file is found.
        '''

        import cpenv
        self.log('Checking job scene file for module requirements...')

        scene_file = job.GetJobPluginInfoKeyValue('SceneFile')
        if not scene_file:
            self.log('  SceneFile not set...')
            return

        requirement = os.path.dirname(scene_file)
        try:
            resolved = cpenv.resolve([requirement])
            return resolved
        except cpenv.ResolveError:
            pass

    def resolve_from_job_plugin(self, plugin_mapping, job_plugin):
        '''Attempt to resolve modules using the Autocpenv event plugins
        configured plugin mapping.
        '''

        import cpenv
        self.log('Checking job plugin_mapping for module requirements...')

        plugin_mapping = plugin_mapping_to_dict(plugin_mapping)
        requirements = plugin_mapping.get(job_plugin, None)

        if not requirements:
            self.log('  No plugin mapping for ' + job_plugin)
            return

        try:
            resolved = cpenv.resolve(requirements)
            return resolved
        except cpenv.ResolveError:
            pass


class EventLogReporter(object):

    # Injected in _load_cpenv
    log = None

    def start_resolve(self, requirements):
        self.log('- Resolving requirements...')

    def resolve_requirement(self, requirement, module_spec):
        self.log('  %s - %s' % (module_spec.real_name, module_spec.path))

    def end_resolve(self, resolved, unresolved):
        if unresolved:
            self.log('  Failed to resolve %s' % ', '.join(unresolved))

    def start_localize(self, module_specs):
        self.log('- Localizing modules...')

    def end_localize(self, modules):
        pass

    def start_progress(self, label, max_size, data):

        if 'download' in label.lower():
            spec = data['module_spec']
            self.log(
                '  Downloading %s from %s...' %
                (spec.qual_name, spec.repo.name)
            )
        elif 'upload' in label.lower():
            module = data['module']
            to_repo = data['to_repo']
            self.log(
                '  Uploading %s to %s...' %
                (module.qual_name, to_repo.name)
            )
        else:
            self.log('  ' + label)


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
    return [part for part in path.split(pathsep) if part]


def plugin_mapping_to_dict(plugin_mapping):
    '''Convert the plugin_mapping config entry to a dictionary'''

    d = {}

    for line in plugin_mapping.split(';'):
        plugin, env_paths = line.split('=')
        d.setdefault(plugin, env_paths.split())

    return d
