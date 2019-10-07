=========
autocpenv
=========

Deadline Event Plugin that automatically activates a cpenv environment when a slave starts rendering a task.


Installation
============
Clone this git repository into your Deadline repository's custom events location::

    cd DEADLINE_REPOSITORY_PATH/custom/events
    git clone https://github.com/cpenv/autocpenv.git

Use git pull to upgrade autocpenv::

    cd DEADLINE_REPOSITORY_PATH/custom/events/autocpenv
    git pull origin master


Configuration
=============
Open Deadline Monitor and enable *super user* mode under the tools menu. Then open the *Configure Event Plugins* dialog from the tools menu.

.. image:: config_dialog.png
    :alt: autocpenv Config Dialog
    :align: center

Options
-------

- State: How this event plug-in should respond to events. If Global, all jobs and slaves will trigger the events for this plugin. If Opt-In, jobs and slaves can choose to trigger the events for this plugin. If Disabled, no events are triggered for this plugin.
- CPENV_HOME: Root path to cpenv environments
- CPENV_MODULES: Root path to cpenv modules
- Plugin Mapping: Mapping of deadline plugins to cpenv environments. Each line should start with a deadline plugin and end with a space separate list of cpenv environment paths.
 - Each line configures a Deadline Plugin
 - **{Deadline_Plugin}={cpenv_module}**
- Logging Level

Documentation
=============
Visit the `cpenv documentation <http://cpenv.readthedocs.org/en/latest>`_ for additional help.
