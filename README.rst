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

- Enabled: set to True to enable autocpenv
- Environment: path to the cpenv environment you'd like to use
- Application Module Mapping: defines which cpenv environment module to activate for each Deadline Plugin
  - Each line configures a Deadline Plugin
  - **{Deadline_Plugin}={cpenv_module}**
- Verbose Logging Level: logging level

Documentation
=============
Visit the `cpenv documentation <http://cpenv.readthedocs.org/en/latest>`_ for additional help.
