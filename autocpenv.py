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
    Listen for OnSlaveStartingJob events then activate the configured cpenv
    environment and modules.
    '''

    def __init__(self):
        self.OnJobSubmittedCallback += self.OnJobSubmitted
        self._log_prefix = ''

    def Cleanup(self):
        del self.OnJobSubmittedCallback

    def log(self, message):
        '''Wraps LogInfo to add a prefix to all log messages.'''

        self.LogInfo('{}{}'.format(self._log_prefix, message))

    def OnJobSubmitted(self, job):
        '''
        Responsible for resolving modules and setting a Job's environment
        variables.
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
        requirements = return_first_result(
            (self.resolve_from_job_extra_info, (job,)),
            (self.resolve_from_job_environment, (job,)),
            (self.resolve_from_environment, (job,)),
            (self.resolve_from_job_scenefile, (job,)),
            (self.resolve_from_job_plugin, (plugin_mapping, job_plugin)),
        )

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

    def resolve_from_job_extra_info(self, job):
        '''Checks to see if the job was submitted with cpenv_requirements.'''

        self.log('Checking job extra info for module requirements...')

        requirements = job.GetJobExtraInfoKeyValue('cpenv_requirements')
        if not requirements:
            plugin.LogInfo('Job has no cpenv requirements...')
            return

        return requirements.split()

    def resolve_from_job_environment(self, job):
        '''Resolve modules from job CPENV_ACTIVE_MODULES variable.'''

        self.log('Checking job environment for module requirements...')

        requirements = job.GetJobEnvironmentKeyValue('CPENV_ACTIVE_MODULES')
        if not requirements:
            self.log('  CPENV_ACTIVE_MODULES not set...')
            return

        return split_path(requirements)

    def resolve_from_environment(self, job):
        '''Checks the environment of the local machine that's submitting the
        job for the CPENV_ACTIVE_MODULES variable.'''

        self.log('Checking local environment for module requirements...')

        requirements = os.getenv('CPENV_ACTIVE_MODULES')
        if not requirements:
            self.log('  CPENV_ACTIVE_MODULES not set...')
            return

        return split_path(requirements)

    def resolve_from_job_scenefile(self, job):
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

    def resolve_from_job_plugin(self, plugin_mapping, job_plugin):
        '''Attempt to resolve modules using the Autocpenv event plugins
        configured plugin mapping.
        '''

        self.log('Checking job plugin_mapping for module requirements...')

        plugin_mapping = plugin_mapping_to_dict(plugin_mapping)
        requirements = plugin_mapping.get(job_plugin, None)
        return requirements


class EventLogReporter(cpenv.Reporter):

    def __init__(self, log):
        super(EventLogReporter, self).__init__()
        self.log = log

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


def return_first_result(*funcs):
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
    cpenv.set_reporter(EventLogReporter(log_method))


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
