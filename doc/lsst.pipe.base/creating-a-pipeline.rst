###################
Creating a Pipeline
###################

**Note**
This guide will assume some knowledge about
`PipelineTasks`\ s, and so if you would like you can check out
:doc:`Creating a PipelineTask <creating-a-pipelinetask.rst>` for info on what
a `PipelineTask` is and how to make one. However, this guide attempts to be
mostly stand alone, and should be readable with minimal references.

....

`PipelineTask`\ s are bits of algorithmic code that define what data they need
as input, and what they will produce as an output. `Pipeline`\ s are high level
documents that create a specification that is used to run one or more
`PipelineTask`\ s. This how-to guide guide will introduce you to the basic
syntax of a `Pipeline` document, and progressively take you through;
configuring tasks, verifying configuration, specifying subsets of tasks,
creating `Pipeline`\ s using composition, a basic introduction to running
`Pipeline`\ s, and discussing common conventions when creating `Pipelines`.

A Basic Pipeline
----------------
`Pipeline` documents are written using yaml syntax. If you are unfamiliar with 
yaml, there are many guides across the internet, but the basic idea is that it
is a simple markup language to describe key, value mappings, and lists of
values (which may be further mappings).

`Pipelines` have two required keys, ``description`` and ``tasks``. The value
associated with the ``description`` should provide a reader an understanding of
what the pipeline is intended to do and is written as plain text.

The second required key is ``tasks``. This section defines what work this
pipeline will do. Unlike ``description`` that has plain text as a value, the
'value' associated with the ``tasks`` keys is another key, value mapping. The
keys of this inner mapping are labels which will be used to refer to an
individual task. These labels can be any name you choose, the only
restriction is that they must be unique amongst all the tasks. The values in
this mapping can be a number of things, which you will see through the course
of this guide, but the most basic is a string that gives the fully qualified
`PipelineTask` that is to be run.

This is a lot of text to digest, so take a look at the following example as a
'picture' is worth a thousand words.

.. code-block:: yaml

    description: A demo pipeline in the how-to guide
    tasks:
      characterizeImage:  lsst.pipe.tasks.characterizeImage.CharacterizeImageTask

This is all it takes to have a simple `Pipeline`, noting that the declaration
would normally be in a file with a .yaml extension. The ``description``
reflects that this `Pipeline` is intended just for this guide. The ``tasks``
section contains only one entry. The label used for this entry,
``characterizeImage``, happens to match the module of the task it points to.
It could have been anything, but the name was suitably descriptive, so it was
a good choice.

If run this `Pipeline` would execute `CharacterizeImageTask`, process the
data-sets declared in that task and write the declared outputs.

Having a pipeline to run a single `PipelineTask` does not seem very useful.
The example below is a bit more realistic.

.. code-block:: yaml

    description: A demo pipeline in the how-to guide
    tasks:
      isr: lsst.ip.isr.IsrTask
      characterizeImage: lsst.pipe.tasks.characterizeImage.CharacterizeImageTask
      calibrate: lsst.pipe.tasks.calibrate.CalibrateTask

This `Pipeline` contains 3 tasks to run, all of which are used to do single
frame processing. The order that the tasks are executed is not determined by
the ordering of the tasks in the pipeline. The following `Pipeline` is exactly
the same from an execution point of view.

.. code-block:: yaml

    description: A demo pipeline in the how-to guide
    tasks:
      characterizeImage: lsst.pipe.tasks.characterizeImage.CharacterizeImageTask
      calibrate: lsst.pipe.tasks.calibrate.CalibrateTask
      isr: lsst.ip.isr.IsrTask

Tasks define their inputs and outputs which are used to construct an
execution graph of the specified tasks. A consequence of this is if a
pipeline does not define all the tasks required to generate all needed inputs
and outputs it will get caught before any execution occurs.

Configuring Tasks
-----------------
Often `PipelineTasks` (and their subtasks) contain a multitude of
configuration options that alter the way the task executes. Because
`Pipeline`\ s are designed to do a specific type of processing (per the
description field) some tasks may need specific configurations set to
enable/disable behavior in the context of a `Pipeline`.

To configure a task associated with a particular label, the value associated 
with the label must be changed from the qualified task name to a new
sub-mapping. This new sub mapping should have two keys, ``class`` and
``config``.

The ``class`` key should point to the same qualified task name as before. The 
value associated with the ``config`` keyword is itself a mapping where
the configuration values are declared. The example below shows this behavior
in action.

.. code-block:: yaml

  makeWarp:
    class: lsst.pipe.tasks.makeCoaddTempExp.MakeWarpTask
    config:
      matchingKernelSize: 29
      makePsfMatched: true
      modelPsf.defaultFwhm: 7.7
      doApplyExternalPhotoCalib: false
      doApplyExternalSkyWcs: false
      doApplySkyCorr: false
      doWriteEmptyWarps: true

This example shows an entry for
`~lsst.pipe.tasks.makeCoaddTempExp.MakeWarpTask`. The label used for this task 
is ``makeWap`` and the class location is now declared in the sub mapping
alongside the ``class`` keyword. The ``config`` keyword is associated with 
various `~lsst.pex.config.Field`\ s and the configuration appropriate for this 
`Pipeline` specified as an additional yaml mapping.

The complete complexity of `lsst.pex.config` can't be represented with simple
yaml mapping syntax. To account for this, ``config`` blocks in `Pipeline`\ s
support two special fields: ``file`` and ``python``.

The ``file`` key may be associated with either a single value pointing to a
filesystem path where a `lsst.pex.config` file can be found, or a yaml list
of such paths. The file paths can contain environment variables that will be
expanded prior to loading the file(s). These files will then be applied to
the task during configuration time to override any default values.

Sometimes configuration is too complex to express with yaml syntax, yet it is
simple enough that it does not warrant its own config file. The ``python``
key is designed to support this use case. The value associated with the key
is a (possibly multi-line) string with valid python syntax. This string is
evaluated and applied during task configuration exactly as if it had been
written in a file or typed out in an interpreter. The following example expands
the previous one to use the ``python`` key.

.. code-block:: yaml

  makeWarp:
    class: lsst.pipe.tasks.makeCoaddTempExp.MakeWarpTask
    config:
      matchingKernelSize: 29
      makePsfMatched: true
      modelPsf.defaultFwhm: 7.7
      doApplyExternalPhotoCalib: false
      doApplyExternalSkyWcs: false
      doApplySkyCorr: false
      doWriteEmptyWarps: true
      python: "config.warpAndPsfMatch.psfMatch.kernel['AL'].alardSigGauss = \
        [1.0, 2.0, 4.5]"

Parameters
----------
As you saw in the pervious section, each task defined in a `Pipeline` may
have its own configuration. However, it is sometimes useful for configuration
fields in multiple tasks to share the same value. `Pipeline`\ s support this
with a concept called ``parameters``. This is a top level section in the
`Pipeline` document specified with a key named ``parameters``.

The contents of the ``parameters`` section is a mapping of key, value pairs
where the key is any name chosen by the `Pipeline` author. These keys
(preceded by ``parameters.``) can be used in a tasks config block to indicate
that the value of that configuration field should be filled in with the
associated value in the parameters section.

To make this a bit clearer take a look at the following example, making note
that only config fields relevant for this example are shown.

.. code-block:: yaml

  parameters:
    calibratedSingleFrame: calexp
  tasks:
    calibrate:
      class: lsst.pipe.tasks.calibrate.CalibrateTask
      config:
        connections.outputExposure = parameters.calibratedSingleFrame
    makeWarp:
      class: lsst.pipe.tasks.makeCoaddTempExp.MakeWarpTask
      config:
        connections.calExpList = parameters.calibratedSingleFrame
    forcedPhotCcd:
      class: lsst.meas.base.forcedPhotCcd.ForcedPhotCcdTask
      config:
        connections.exposure = parameters.calibratedSingleFrame

The above example used ``parameters`` to link the dataset type names for
multiple tasks, but ``parameters`` can be used anywhere that more than one
config field use the same value.

FINDME introduces how to run `Pipeline`\ s and will talk about how to
dynamically set a parameters value at `Pipeline` invocation time.

Verifying Configuration: Contracts
----------------------------------
The `~lsst.pipe.base.config.Config` classes associated with
`~lsst.pipe.base.task.Task`\ s provide a method named ``verify`` which can be
used to verify that all supplied configuration is valid. These verify methods
however, are shared by every instance of the config class. This means they
can not be specialized for the context in which the task is being used.

When writing `Pipelines` it is important to verify that configuration values
are set in such a way to ensure consistent behavior among all the defined
tasks. `Pipelines` support this sort of behavior with a concept called
``contracts``. These ``contracts`` are useful for ensuring two separate
config fields are set to the same value, or ensuring a config parameter is
set to a required value in the context of this pipeline. Because
configuration values can be set anywhere from the `Pipeline` definition to
the command-line invocation of the pipeline, these ``contracts`` ensure that
required configuration is appropriate prior to execution.

``contracts`` are expressions written with Python syntax that should evaluate
to a boolean value. If any ``contract`` evaluates to false, the `Pipeline`
configuration is deemed to be in consistent, an error is raised, and
execution of the `Pipeline` is halted.

Defining contracts involves adding a new top level key to your document named
``contracts``. The value associated with this key is a yaml list of
individual contracts. Each list member may either be the ``contract``
expression or a mapping of the expression and a message to raise if the
contract is violated. If the contract is defined as a mapping, the expression
is associated with a key named ``contract`` and the message is a simple string
associated with a key named ``msg``.

The expression section of ``contracts`` make reference to configuration
parameters for one or more tasks. These expressions make use of the label
assigned to a task in the ``tasks`` section to indicate which task a
configuration parameter belongs to. The syntax is similar to that of a pex
config file where the ``config`` variable is replaced with the task label
associated with the task to configure. Take a look at a contract for the
``DRP.yaml`` `Pipeline` for an example.

.. code-block:: yaml

    contracts:
      - contract: "makeWarp.matchingKernelSize ==\
                   assembleCoadd.matchingKernelSize"
        msg: "The warping kernel size must be consistent between makeWarp and 
              assembleCoadd tasks"

It is important to note how ``contracts`` relate to ``parameters``. While a
``parameter`` can be used to set two configuration variables to the same
value at the time `Pipeline` definition is read, it does not offer any
validation. It is possible for someone to change the configuration of one of
the fields before a `Pipeline` is run. Because of this, ``contracts`` should
always be written without regards to how ``parameters`` are used.

Subsets
-------
`Pipelines` are the definition of a processing workflow from some input data
products to some output data products. Frequently, however, there are sub
units within a `Pipeline` that define a useful unit of the `Pipeline` to run
on their own. This may be something like processing single frames only.

You, as the author of the `Pipeline`, can define one or more of the
processing units by creating a section in your `Pipeline` named ``subsets``.
The value associated with the ``subsets`` key is a new mapping. The keys of
this mapping will be the labels used to refer to an individual ``subset``.
The values of this mapping can either be a yaml list of the tasks labels to
be associated with this subset, or another yaml mapping. If it is the latter,
the keys must be ``subset``, which is associated with the yaml list of task
labels, and ``description``, which is associated with a descriptive message
of what the subset is meant to do. Take a look at the following two examples
which show the same ``subset`` defined in both styles.

.. code-block:: yaml

  subsets:
    processCcd:
      - isr
      - characterizeImage
      - calibrate

.. code-block:: yaml

  subsets:
    processCcd:
      subset:
        - isr
        - characterizeImage
        - calibrate
      description: A set of tasks to run when doing single frame processing