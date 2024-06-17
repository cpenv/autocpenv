# -*- coding: utf-8 -*-
from __future__ import print_function

import json
import os
import sys

# Standard library imports
from fnmatch import fnmatch

# Deadline imports
from Deadline.Events import DeadlineEventListener
from Deadline.Scripting import RepositoryUtils

# .Net imports
from System.Diagnostics import *
from System.IO import *

# Setup system path
this_path = RepositoryUtils.GetEventPluginDirectory("autocpenv")
packages_path = os.path.join(this_path, "packages")
if packages_path not in sys.path:
    sys.path.insert(1, packages_path)


import cpenv
from cpenv import mappings


def GetDeadlineEventListener():
    return AutoCpenv()


def CleanupDeadlineEventListener(eventListener):
    eventListener.Cleanup()


class AutoCpenv(DeadlineEventListener):
    """
    Listen for OnSlaveStartingJob events then activate the configured cpenv
    environment and modules.
    """

    def __init__(self):
        if sys.version_info.major == 3:
            super().__init__()
        self.OnJobSubmittedCallback += self.OnJobSubmitted
        self._log_prefix = ""

    def Cleanup(self):
        del self.OnJobSubmittedCallback

    def log(self, message):
        """Wraps LogInfo to add a prefix to all log messages."""

        self.LogInfo("{}{}".format(self._log_prefix, message))

    def OnJobSubmitted(self, job):
        """
        Responsible for resolving modules and setting a Job's environment
        variables.
        """

        job_plugin = job.JobPlugin
        plugin_mapping = self.GetConfigEntry("plugin_mapping")

        self.log("Checking job ExtraInfo for requirements...")
        requirements = job.GetJobExtraInfoKeyValue("cpenv_requirements")
        if requirements:
            requirements = requirements.split()
            self.log("Found {} requirements...".format(len(requirements)))
            for requirement in requirements:
                self.log("  " + requirement)
            return

        # read config and setup cpenv
        configure_autocpenv(self.log)

        self.log("Attempting to find requirements...")
        requirements = return_first_result(
            (self.collect_from_job_extra_info, (job,)),
            (self.collect_from_job_environment, (job,)),
            (self.collect_from_environment, (job,)),
            (self.collect_from_job_scenefile, (job,)),
            (self.collect_from_job_plugin, (plugin_mapping, job_plugin)),
        )
        if not requirements:
            self.log("  Did not find any job requirements...")
        else:
            self.log("  Found requirements: " + " ".join(requirements))

        forced_requirements = self.collect_from_forced_plugin_mappings(job_plugin)
        if forced_requirements:
            if requirements:
                requirements = combine_requirements(requirements, forced_requirements)
            else:
                requirements = forced_requirements

        if requirements:
            # print the merged requirements we found...
            self.log("Found {} requirements...".format(len(requirements)))
            for requirement in requirements:
                self.log("  " + requirement)
        else:
            # we dont have any job requirements or forced requirements, do nothing...
            self.log("Did not find any requirements for this job...")
            return

        # set the job cpenv requirements on the jobExtraInfo key
        self.log("Setting JobExtranInfo cpenv_requirements")
        job.SetJobExtraInfoKeyValue("cpenv_requirements", " ".join(requirements))

        self.log("Saving Job.")
        RepositoryUtils.SaveJob(job)

    def collect_from_job_extra_info(self, job):
        """Checks to see if the job was submitted with cpenv_requirements."""

        self.log("Checking job extra info for module requirements...")

        requirements = job.GetJobExtraInfoKeyValue("cpenv_requirements")
        if not requirements:
            self.log("  Job has no cpenv requirements...")
            return

        return requirements.split()

    def collect_from_job_environment(self, job):
        """Resolve modules from job CPENV_ACTIVE_MODULES variable."""

        self.log("Checking job environment for module requirements...")

        requirements = job.GetJobEnvironmentKeyValue("CPENV_ACTIVE_MODULES")
        if not requirements:
            self.log("  CPENV_ACTIVE_MODULES not set...")
            return

        return split_path(requirements)

    def collect_from_environment(self, job):
        """Checks the environment of the local machine that's submitting the
        job for the CPENV_ACTIVE_MODULES variable."""

        self.log("Checking local environment for module requirements...")

        requirements = os.getenv("CPENV_ACTIVE_MODULES")
        if not requirements:
            self.log("  CPENV_ACTIVE_MODULES not set...")
            return

        return split_path(requirements)

    def collect_from_job_scenefile(self, job):
        """Attempt to resolve modules from the jobs scene_file.

        Walks up the path until a .cpenv file is found.
        """

        self.log("Checking job scene file for module requirements...")

        scene_file = job.GetJobPluginInfoKeyValue("SceneFile")
        if not scene_file:
            self.log("  SceneFile not set...")
            return

        requirement = os.path.dirname(scene_file)
        try:
            resolved = cpenv.resolve([requirement])
            return [m.qual_name for m in resolved]
        except cpenv.ResolveError:
            pass

    def _collect_from_plugin_mapping(self, plugin_mapping, job_plugin):
        if not plugin_mapping:
            return
        plugin_mapping = plugin_mapping_str_to_dict(plugin_mapping)
        requirements = plugin_mapping.get(job_plugin, None)
        return requirements

    def collect_from_job_plugin(self, plugin_mapping, job_plugin):
        """Attempt to resolve modules using the Autocpenv event plugins
        configured plugin mapping.
        """

        self.log("Checking plugin_mapping for module requirements...")

        requirements = self._collect_from_plugin_mapping(plugin_mapping, job_plugin)
        if not requirements:
            self.log("  Job plugin has no module requirements...")

        return requirements

    def collect_from_forced_plugin_mappings(self, job_plugin):
        """Attempt to resolve modules from the autocpenv forced plugin mappings setting"""

        self.log("Checking forced_plugin_mapping for module requirements...")

        requirements = self._collect_from_plugin_mapping(
            self.GetConfigEntry("forced_plugin_mapping"),
            job_plugin,
        )
        if requirements:
            self.log("  Forced requirements found: " + " ".join(requirements))
        else:
            self.log("  Job plugin has no forced requirements...")

        return requirements


class EventLogReporter(cpenv.Reporter):
    def __init__(self, log):
        super(EventLogReporter, self).__init__()
        self.log = log

    def start_resolve(self, requirements):
        self.log("- Resolving requirements...")

    def resolve_requirement(self, requirement, module_spec):
        self.log("  %s - %s" % (module_spec.qual_name, module_spec.path))

    def end_resolve(self, resolved, unresolved):
        if unresolved:
            self.log("  Failed to resolve %s" % ", ".join(unresolved))

    def start_localize(self, module_specs):
        self.log("- Localizing modules...")

    def start_progress(self, label, max_size, data):
        if "download" in label.lower():
            spec = data["module_spec"]
            self.log("  Downloading %s from %s..." % (spec.qual_name, spec.repo.name))
        elif "upload" in label.lower():
            module = data["module"]
            to_repo = data["to_repo"]
            self.log("  Uploading %s to %s..." % (module.qual_name, to_repo.name))
        else:
            self.log("  " + label)


def combine_requirements(a, b):
    """Combines two list of requirements, returning the requirements with the
    highest version numbers."""

    try:
        all_requirements = {}
        for requirement in a + b:
            name, version = cpenv.module.parse_module_requirement(requirement)
            all_requirements.setdefault(name, [])
            all_requirements[name].append((version, requirement))

        results = []
        for name, matches in all_requirements.items():
            results.append(max(matches, lambda m: m[0])[1])

        return results
    except:
        # TODO: Exception for the following issue:
        # An error occurred in the "OnJobSubmitted" function in events plugin 'autocpenv': '>'
        # not supported between instances of 'function' and 'list' (Python.Runtime.PythonException)
        return a + b


def return_first_result(*funcs):
    for func, args in funcs:
        result = func(*args)
        if result:
            return result


def split_path(path, pathsep=os.pathsep):
    return [part for part in path.split(pathsep) if part]


def plugin_mapping_str_to_dict(plugin_mapping):
    """Convert the plugin_mapping config entry to a dictionary"""

    d = {}
    if not plugin_mapping:
        return d

    for line in plugin_mapping.split(";"):
        plugin, env_paths = line.split("=")
        d.setdefault(plugin, env_paths.split())

    return d


def repos_str_to_list(repos):
    """Convert the repos config entry to a list of dicts"""

    if not repos:
        return []

    decoded = json.loads(repos.replace(";", "\n"))
    if isinstance(decoded, dict):
        return [decoded]
    elif isinstance(decoded, list):
        return decoded
    else:
        raise ValueError("Invalid value for autocpenv repositories.")


def get_config(log=None, worker=None):
    """Load config from Event Plugin Config.

    Provide a worker name to lookup group specific config sections.
    """

    log = log or print
    plugin_config = RepositoryUtils.GetEventPluginConfig("autocpenv")
    defaults = {
        "state": plugin_config.GetConfigEntry("State"),
        "home_path": plugin_config.GetConfigEntry("cpenv_home"),
        "repos": repos_str_to_list(plugin_config.GetConfigEntry("repos")),
        "ignore_missing": plugin_config.GetBooleanConfigEntry("ignore_missing"),
        "plugin_mapping": plugin_mapping_str_to_dict(
            plugin_config.GetConfigEntry("plugin_mapping")
        ),
        "forced_plugin_mapping": plugin_mapping_str_to_dict(
            plugin_config.GetConfigEntry("forced_plugin_mapping")
        ),
    }

    if not worker:
        log("Using default config...")
        return defaults

    group_configs = {}
    keys = plugin_config.GetConfigKeys()
    for i in range(10)[::-1]:
        section = f"Group{i}"
        if f"{section}_enable" not in keys:
            continue

        enabled = plugin_config.GetBooleanConfigEntry(f"{section}_enable")
        group = plugin_config.GetConfigEntry(f"{section}_group")
        if not enabled or not group:
            continue

        group_configs[group] = {
            "home_path": plugin_config.GetConfigEntry(f"{section}_cpenv_home"),
            "repos": repos_str_to_list(
                plugin_config.GetConfigEntry(f"{section}_repos")
            ),
            "ignore_missing": plugin_config.GetBooleanConfigEntry(
                f"{section}_ignore_missing"
            ),
        }

    worker_config = defaults
    settings = RepositoryUtils.GetSlaveSettings(worker, True)
    for group in group_configs:
        if group in settings.SlaveGroups:
            log(f'Using config Group overrides "{group}" for worker "{worker}"...')
            worker_config.update(group_configs[group])
            break

    return worker_config


def configure_autocpenv(log=None, worker=None):
    """Read config from EventPlugin and setup cpenv."""

    log = log or print
    if not worker:
        log("Configuring cpenv...")
    else:
        log(f"Configuring cpenv for worker {worker}...")

    autocpenv = RepositoryUtils.GetEventPluginDirectory("autocpenv")
    if autocpenv not in sys.path:
        sys.path.insert(1, autocpenv)
        sys.path.insert(1, autocpenv + "/packages")

    config = get_config(log, worker)

    # Set home path
    home_path = config.get("home_path")
    if home_path:
        log(f"Setting CPENV_HOME to {home_path}")
        cpenv.set_home_path(home_path)

    # Setup Repositories
    for repo in config.get("repos", []):
        from cpenv.repos import registry as repo_types

        log(f"Configuring Repository {repo['name']}...")
        repo_type = repo.pop("type")
        try:
            repo_cls = repo_types[repo_type]
            cpenv.add_repo(repo_cls(**repo))
        except Exception as e:
            log(f"Failed to create {repo_type} repo named {repo['name']}\nError: {e}")

    # Setup reporting
    cpenv.set_reporter(EventLogReporter(log))

    return config


def match_any(value, patterns):
    """Uses fnmatch to match a value against multiple glob-style patterns."""

    for pattern in patterns:
        if fnmatch(value, pattern):
            return True
    return False


def is_jobpreload_enabled(job=None, worker=None):
    """Return True if the jobpreload script should execute...."""

    plugin_config = RepositoryUtils.GetEventPluginConfig("autocpenv")
    opt_outs = [s for s in plugin_config.GetConfigEntry("opt_out").split() if s]
    state = plugin_config.GetConfigEntry("State")

    if job:
        if job.SuppressEvents:
            return False, "Job is suppressing events."
        if opt_outs and job.JobGroup and match_any(job.JobGroup, opt_outs):
            return False, f"Job Group '{job.JobGroup}' matched Opt-Out pattern."

    if worker:
        settings = RepositoryUtils.GetSlaveSettings(worker, True)
        if opt_outs:
            for group in settings.SlaveGroups:
                if match_any(group, opt_outs):
                    return False, f"Worker Group '{group}' matched Opt-Out pattern."
            if match_any(worker, opt_outs):
                return False, f"Worker Name '{worker}' matched Opt-Out pattern.'"

    if state == "Disabled":
        return False, "Event plugin is Disabled."

    if state == "Global Enabled":
        return True, "Event plugin is Enabled!"


def GlobalJobPreLoad(plugin):
    """Execute this method in your GlobalJobPreLoad.py file.

    See GlobalJobPreLoad.py for reference. Or if you are not using a
    GlobalJobPreLoad script simply copy the file to <repo>/custom/plugins.
    """
    plugin.LogInfo("CPENV: Executing GlobalJobPreload...")

    job = plugin.GetJob()
    worker = plugin.GetSlaveName()

    enabled, message = is_jobpreload_enabled(job, worker)
    if not enabled:
        plugin.LogInfo(f"Skipping: {message}")
        return

    # Get job cpenv requirements
    requirements = job.GetJobExtraInfoKeyValue("cpenv_requirements")
    if not requirements:
        plugin.LogInfo("Skipping: Job has no cpenv requirements.")
        return

    # Read config from autocpenv EventPlugin
    config = configure_autocpenv(plugin.LogInfo, worker)

    # Use cpenv to resolve our requirements and get the combined environment variables
    resolved = cpenv.resolve(requirements.split(), config.get("ignore_missing", False))
    localized = cpenv.Localizer().localize(resolved)
    environment = cpenv.Activator().combine_modules(localized)

    plugin.LogInfo("Collecting process and job environment variables...")
    proc_environment = {}
    for key in environment.keys():
        proc_env_var = plugin.GetProcessEnvironmentVariable(key)
        if proc_env_var:
            proc_environment[key] = proc_env_var

    plugin.LogInfo("Merging environment variables...")
    job_environment = mappings.dict_to_env(
        mappings.join_dicts(
            proc_environment,
            environment,
        )
    )
    job_environment = mappings.expand_envvars(job_environment)

    plugin.LogInfo("Setting process environment variables...")
    for k, v in job_environment.items():
        plugin.SetProcessEnvironmentVariable(k, v)

    plugin.LogInfo("CPENV: GlobalJobPreload Done!")
