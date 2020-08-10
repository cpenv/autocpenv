# -*- coding: utf-8 -*-
from __future__ import print_function

# Standard library imports
import sys
import os

# IronPython imports
from System.Diagnostics import *
from System.IO import *

# Deadline imports
from Deadline.Events import *
from Deadline.Scripting import *
from Deadline.Slaves import *


# Setup system path
this_path = RepositoryUtils.GetEventPluginDirectory("autocpenv")
packages_path = os.path.join(this_path, 'packages')
if packages_path not in sys.path:
    sys.path.insert(1, packages_path)


import cpenv
from cpenv import mappings


def GetDeadlineEventListener():
    return AutoCpenv()


def CleanupDeadlineEventListener(eventListener):
    eventListener.Cleanup()


class AutoCpenv(DeadlineEventListener):
    '''
    Listens for OnJobSumitted and OnSlaveStartingJob events. In OnJobSubmitted
    the cpenv_requirements extrainfo key is set. In OnSlaveStartingJob those
    requirements are used to activate modules per worker. This ensures that
    modules are localized to each worker and environment variables are set
    based on the worker's platform.

    # TODO: OnSlaveStartingJobCallback is disabled because I'm not sure how
    #       to set process environment variables there yet. Still using the
    #       GlobalJobPreLoad.py file for the time being. With the goal of
    #       moving that logic into the OnSlaveStartingJob method.
    '''

    def __init__(self):
        self._log_prefix = ''

        self.OnJobSubmittedCallback += self.OnJobSubmitted
        self.OnSlaveStartingJobCallback += self.OnSlaveStartingJob

    def Cleanup(self):
        del self.OnJobSubmittedCallback
        del self.OnSlaveStartingJobCallback

    def log(self, message):
        '''Wraps LogInfo to add a prefix to all log messages.'''

        self.LogInfo('{}{}'.format(self._log_prefix, message))

    def OnJobSubmitted(self, job):
        '''
        Responsible for finding cpenv requirements for a job and setting
        the cpenv_requirements extrainfo key. Later in the OnSlaveStartingJob
        callback these requirements are used to activate modules for
        each worker.
        '''

        job_plugin = job.JobPlugin
        plugin_mapping = self.GetConfigEntry('plugin_mapping')

        self.log('Checking job ExtraInfo for requirements...')
        requirements = job.GetJobExtraInfoKeyValue('cpenv_requirements')
        if requirements:
            requirements = requirements.split()
            self.log('Found {} requirements...'.format(len(requirements)))
            for requirement in requirements:
                self.log('  ' + requirement)
            return

        # read config and setup cpenv
        configure_autocpenv(self.log)

        self.log('Attempting to find requirements...')
        requirements = self.find_requirements(job, job_plugin, plugin_mapping)

        if not requirements:
            self.log('Error! Failed 4 attempts to find requirements...')
            return
        else:
            self.log('Found {} requirements...'.format(len(requirements)))
            for requirement in requirements:
                self.log('  ' + requirement)

        self.log('Setting JobExtranInfo cpenv_requirements')
        job.SetJobExtraInfoKeyValue(
            'cpenv_requirements',
            ' '.join(requirements)
        )

        self.log('Saving Job.')
        RepositoryUtils.SaveJob(job)

    def OnSlaveStartingJob(self, string, job):
        '''
        Responsible for activating modules saved in the cpenv_requirements
        extrainfo key for a job. Each worker must activate modules themselves,
        which will cause them to localize modules, then set environment
        variables specific to the workers machine.
        '''

        # Get job cpenv requirements
        requirements = job.GetJobExtraInfoKeyValue('cpenv_requirements')
        if not requirements:
            self.log(
                'Skipping cpenv OnSlaveStartingJob: '
                'Job has no cpenv requirements.'
            )
            return

        # read config and setup cpenv
        configure_autocpenv(self.log)

        # activate requirements
        requirements = requirements.split()
        try:
            modules = cpenv.activate(requirements)
            self.log('- Activated {} modules...'.format(len(modules)))
        except Exception:
            self.log('Failed to activate cpenv modules.')
            self.log(traceback.format_exc())

        self.log('- Worker Environment...')
        for k, v in sorted(os.environ.items()):
            self.log('  {}: {}'.format(k, v))

    def find_requirements(self, job, job_plugin, plugin_mapping):
        '''Attempts to locate the requirements for a job.

        1. In the current process' os.environ
        2. In the current job's Environment
        3. Resolved from the job's scenefile (.cpenv file could be present)
        4. From the autocpenv plugin_mapping configuration
        '''
        return first_result(
            (self._resolve_from_environment, (job,)),
            (self._resolve_from_job_environment, (job,)),
            (self._resolve_from_job_scenefile, (job,)),
            (self._resolve_from_job_plugin, (plugin_mapping, job_plugin)),
        )

    def _resolve_from_environment(self, job):
        '''Checks the environment of the local machine that's submitting the
        job for the CPENV_ACTIVE_MODULES variable.'''

        self.log('Checking local environment for module requirements...')

        requirements = os.getenv('CPENV_ACTIVE_MODULES')
        if not requirements:
            self.log('  CPENV_ACTIVE_MODULES not set...')
            return

        return split_path(requirements)

    def _resolve_from_job_environment(self, job):
        '''Resolve modules from job CPENV_ACTIVE_MODULES variable.'''

        self.log('Checking job environment for module requirements...')

        requirements = job.GetJobEnvironmentKeyValue('CPENV_ACTIVE_MODULES')
        if not requirements:
            self.log('  CPENV_ACTIVE_MODULES not set...')
            return

        return split_path(requirements)

    def _resolve_from_job_scenefile(self, job):
        '''Attempt to resolve modules from the jobs scene_file.

        Walks up the path until a .cpenv file is found.
        '''

        self.log('Checking job scene file for module requirements...')

        scene_file = job.GetJobPluginInfoKeyValue('SceneFile')
        if not scene_file:
            self.log('  SceneFile not set...')
            return

        requirement = os.path.dirname(scene_file)
        try:
            resolved = cpenv.resolve([requirement])
            return [m.qual_name for m in resolved]
        except cpenv.ResolveError:
            pass

    def _resolve_from_job_plugin(self, plugin_mapping, job_plugin):
        '''Attempt to resolve modules using the Autocpenv event plugins
        configured plugin mapping.
        '''

        self.log('Checking job plugin_mapping for module requirements...')

        plugin_mapping = plugin_mapping_to_dict(plugin_mapping)
        requirements = plugin_mapping.get(job_plugin, None)
        return requirements


class EventLogReporter(object):

    log = None  # Injected in GlobalJobPreLoad

    def start_resolve(self, requirements):
        self.log('- Resolving requirements...')

    def resolve_requirement(self, requirement, module_spec):
        self.log('  %s - %s' % (module_spec.real_name, module_spec.path))

    def end_resolve(self, resolved, unresolved):
        if unresolved:
            self.log('  Failed to resolve %s' % ', '.join(unresolved))

    def start_localize(self, module_specs):
        self.log('- Localizing modules...')

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


def first_result(*funcs):
    '''Returns the first non-None result from a list of funcs.'''

    for func, args in funcs:
        result = func(*args)
        if result:
            return result


def split_path(path, pathsep=os.pathsep):
    return [part for part in path.split(pathsep) if part]


def plugin_mapping_to_dict(plugin_mapping):
    '''Convert the plugin_mapping config entry to a dictionary'''

    d = {}

    for line in plugin_mapping.split(';'):
        plugin, env_paths = line.split('=')
        d.setdefault(plugin, env_paths.split())

    return d


def configure_autocpenv(log_method=None):
    '''Read config from EventPlugin and setup cpenv.'''

    log_method = log_method or print
    log_method('Configuring cpenv...')
    autocpenv = RepositoryUtils.GetEventPluginDirectory('autocpenv')
    if autocpenv not in sys.path:
        sys.path.insert(1, autocpenv)
        sys.path.insert(1, autocpenv + '/packages')

    config = RepositoryUtils.GetEventPluginConfig('autocpenv')
    home_path = config.GetConfigEntry('cpenv_home')
    if home_path:
        cpenv.set_home_path(home_path)

    # Initialize ShotgunRepo for requirement lookups
    if config.GetConfigEntry('ShotgunRepo_enable'):
        repo = cpenv.ShotgunRepo(
            name='autocpenv_shotgun',
            base_url=config.GetConfigEntry('ShotgunRepo_base_url'),
            script_name=config.GetConfigEntry('ShotgunRepo_script_name'),
            api_key=config.GetConfigEntry('ShotgunRepo_api_key'),
        )
        log_method('Adding ShotgunRepo: ' + repo.base_url)
        cpenv.add_repo(repo)

    # Setup reporting
    class _EventLogReporter(EventLogReporter, cpenv.Reporter):
        '''Inject log method and mix with cpenv.Reporter baseclass.'''
        log = log_method

    cpenv.set_reporter(_EventLogReporter)


def GlobalJobPreLoad(plugin):
    '''Execute this method in your GlobalJobPreLoad.py file.

    See GlobalJobPreLoad.py for reference. Or if you are not using a
    GlobalJobPreLoad script simply copy the file to <repo>/custom/plugins.
    '''

    # Get job cpenv requirements
    job = plugin.GetJob()
    requirements = job.GetJobExtraInfoKeyValue('cpenv_requirements')
    if not requirements:
        plugin.LogInfo('Job has no cpenv requirements...')
        return

    # Read config from autocpenv EventPlugin
    configure_autocpenv(plugin.LogInfo)

    # Use cpenv to resolve requirements stored in ExtraInfo
    resolved = cpenv.resolve(requirements.split())
    localizer = cpenv.Localizer(cpenv.get_repo('home'))
    localized = localizer.localize(resolved, overwrite=False)
    activator = cpenv.Activator(localizer)
    env = activator.combine_modules(localized)

    # Get existing environment
    plugin.LogInfo('Collecting process and job environment variables...')
    proc_env = {}
    for key in env.keys():
        proc_env_var = plugin.GetProcessEnvironmentVariable(key)
        if proc_env_var:
            proc_env[key] = proc_env_var

    plugin.LogInfo('Merging environment variables...')
    new_job_env = mappings.dict_to_env(mappings.join_dicts(
        proc_env,
        env,
    ))
    new_job_env = mappings.expand_envvars(new_job_env)

    plugin.LogInfo('Setting process environment variables...')
    for k, v in new_job_env.items():
        plugin.SetProcessEnvironmentVariable(k, v)
