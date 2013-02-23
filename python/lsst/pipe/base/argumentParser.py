#
# LSST Data Management System
# Copyright 2008, 2009, 2010 LSST Corporation.
#
# This product includes software developed by the
# LSST Project (http://www.lsst.org/).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
# GNU General Public License for more details.
#
# You should have received a copy of the LSST License Statement and
# the GNU General Public License along with this program.  If not,
# see <http://www.lsstcorp.org/LegalNotices/>.
#
import argparse
import itertools
import os
import re
import shlex
import sys

import eups
import lsst.pex.logging as pexLog
import lsst.daf.persistence as dafPersist

__all__ = ["ArgumentParser", "ConfigFileAction", "ConfigValueAction",
        "DatasetArgument"]

DEFAULT_INPUT_NAME = "PIPE_INPUT_ROOT"
DEFAULT_CALIB_NAME = "PIPE_CALIB_ROOT"
DEFAULT_OUTPUT_NAME = "PIPE_OUTPUT_ROOT"
DEFAULT_RERUN_NAME = "PIPE_RERUN_ROOT"

def _fixPath(defName, path):
    """Apply environment variable as default root, if present, and abspath
    
    @param defName: name of environment variable containing default root path;
        if the environment variable does not exist then the path is relative
        to the current working directory
    @param path: path relative to default root path
    @return abspath: path that has been expanded, or None if the environment variable does not exist
        and path is None
    """
    defRoot = os.environ.get(defName)
    if defRoot is None:
        if path is None:
            return None
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(defRoot, path or ""))


class ArgumentParser(argparse.ArgumentParser):
    """An argument parser for pipeline tasks that is based on argparse.ArgumentParser
    
    Users may wish to add additional arguments before calling parse_args.
    
    @notes
    * I would prefer to check data ID keys and values as they are parsed,
      but the required information comes from the butler, so I have to construct a butler
      before I do this checking. Constructing a butler is slow, so I only want do it once,
      after parsing the command line, so as to catch syntax errors quickly.
    """
    def __init__(self,
        name,
        usage = "%(prog)s input [options]",
        datasetType = "raw",
        dataRefLevel = None,
    **kwargs):
        """Construct an ArgumentParser
        
        @param name: name of top-level task; used to identify camera-specific override files
        @param usage: usage string
        @param datasetType: dataset type appropriate to the task at hand;
            this affects which data ID keys are recognized.
            Set to an instance of DatasetArgument to accept this from the
            command line
        @param dataRefLevel: the level of the data references returned in dataRefList;
            None uses the data mapper's default, which is usually sensor.
            Warning: any value other than None is likely to be repository-specific.
        @param **kwargs: additional keyword arguments for argparse.ArgumentParser
        """
        self._name = name
        self._dataRefLevel = dataRefLevel
        argparse.ArgumentParser.__init__(self,
            usage = usage,
            fromfile_prefix_chars = '@',
            epilog = """Notes:
* the --rerun option allows the input and output directories to be specified
simultaneously, and relative to the same root.
* --config, --configfile, --id, --trace and @file may appear multiple times;
    all values are used, in order left to right
* @file reads command-line options from the specified file:
    * data may be distributed among multiple lines (e.g. one option per line)
    * data after # is treated as a comment and ignored
    * blank lines and lines starting with # are ignored
* To specify multiple values for an option, do not use = after the option name:
    * wrong: --configfile=foo bar
    * right: --configfile foo bar
* The need to specify camera is temporary
""",
            formatter_class = argparse.RawDescriptionHelpFormatter,
        **kwargs)
        self.add_argument(metavar="INPUT", dest="rawInput",
            help="path to input data repository, relative to $%s" % (DEFAULT_INPUT_NAME,))
        self.add_argument("--calib", dest="rawCalib",
            help="path to input calibration repository, relative to $%s" % (DEFAULT_CALIB_NAME,))
        self.add_argument("--output", dest="rawOutput",
            help="path to output data repository (need not exist), relative to $%s" % (DEFAULT_OUTPUT_NAME,))
        self.add_argument("--rerun", dest="rawRerun", metavar="[INPUT:]OUTPUT",
            help="path to rerun data repository (need not exist), relative to $%s" % (DEFAULT_RERUN_NAME,))
        self.add_argument("--id", nargs="*", action=IdValueAction,
            help="data ID, e.g. --id visit=12345 ccd=1,2", metavar="KEY=VALUE1[^VALUE2[^VALUE3...]")
        if isinstance(datasetType, DatasetArgument):
            self._datasetType = None
            self.add_argument("--datasettype", dest="datasetType",
                required=datasetType.required,
                help=datasetType.help,
                default=datasetType.default)
        else:
            self._datasetType = datasetType
        self.add_argument("-c", "--config", nargs="*", action=ConfigValueAction,
            help="config override(s), e.g. -c foo=newfoo bar.baz=3", metavar="NAME=VALUE")
        self.add_argument("-C", "--configfile", dest="configfile", nargs="*", action=ConfigFileAction,
            help="config override file(s)")
        self.add_argument("-L", "--loglevel", help="logging level")
        self.add_argument("-T", "--trace", nargs="*", action=TraceLevelAction,
            help="trace level for component", metavar="COMPONENT=LEVEL")
        self.add_argument("--debug", action="store_true", help="enable debugging output?")
        self.add_argument("--doraise", action="store_true",
            help="raise an exception on error (else log a message and continue)?")
        self.add_argument("--logdest", help="logging destination")
        self.add_argument("--show", nargs="*", choices="config data exit".split(), default=(),
            help="display final configuration and/or data IDs to stdout? If exit, then don't process data.")
        self.add_argument("-j", "--processes", type=int, default=1, help="Number of processes to use")

    def parse_args(self, config, args=None, log=None, override=None):
        """Parse arguments for a pipeline task

        @param config: config for the task being run
        @param args: argument list; if None use sys.argv[1:]
        @param log: log (instance pex_logging Log); if None use the default log
        @param override: a config override callable, to be applied after camera-specific overrides
            files but before any command-line config overrides.  It should take the root config
            object as its only argument.

        @return namespace: a struct containing many useful fields including:
        - camera: camera name
        - config: the supplied config with all overrides applied, validated and frozen
        - butler: a butler for the data
        - datasetType: dataset type
        - dataIdList: a list of data ID dicts
        - dataRefList: a list of butler data references; each data reference is guaranteed to contain
            data for the specified datasetType (though perhaps at a lower level than the specified level,
            and if so, valid data may not exist for all valid sub-dataIDs)
        - log: a pex_logging log
        - an entry for each command-line argument, with the following exceptions:
          - config is Config, not an override
          - configfile, id, logdest, loglevel are all missing
        - obsPkg: name of obs_ package for this camera
        """
        if args == None:
            args = sys.argv[1:]

        if len(args) < 1 or args[0].startswith("-") or args[0].startswith("@"):
            self.print_help()
            self.exit("%s: error: Must specify input as first argument" % self.prog)

        # Namespace.input and other path arguments are not populated by argparse; they're
        # where we put the processed output from running _fixPath on e.g. namespace.inputRaw.
        # We have to do input in advance because we need to get the mapper before parsing
        # the other arguments.
        # Note that --rerun may change namespace.input, but if it does we verify that the
        # new input has the same mapper class.
        namespace = argparse.Namespace()
        namespace.input = _fixPath(DEFAULT_INPUT_NAME, args[0])
        if not os.path.isdir(namespace.input):
            self.error("Error: input=%r not found" % (namespace.input,))
        
        namespace.config = config
        namespace.log = log if log is not None else pexLog.Log.getDefaultLog()
        namespace.dataIdList = []
        mapperClass = dafPersist.Butler.getMapperClass(namespace.input)
        namespace.camera = mapperClass.getCameraName()
        namespace.obsPkg = mapperClass.getEupsProductName()
        namespace.datasetType = self._datasetType

        self.handleCamera(namespace)

        self._applyInitialOverrides(namespace)
        if override is not None:
            override(namespace.config)
        
        namespace = argparse.ArgumentParser.parse_args(self, args=args, namespace=namespace)
        del namespace.configfile
        del namespace.id
        
        namespace.calib  = _fixPath(DEFAULT_CALIB_NAME,  namespace.rawCalib)
        namespace.output = _fixPath(DEFAULT_OUTPUT_NAME, namespace.rawOutput)
        del namespace.rawInput
        del namespace.rawCalib
        del namespace.rawOutput

        if namespace.rawRerun:
            if namespace.output:
                self.error("Error: cannot specify both --output and --rerun")
            namespace.rerun = tuple(_fixPath(DEFAULT_RERUN_NAME, v) for v in namespace.rawRerun.split(":"))
            modifiedInput = False
            if len(namespace.rerun) == 2:
                namespace.input, namespace.output = namespace.rerun
                modifiedInput = True
            elif len(namespace.rerun) == 1:
                if os.path.exists(namespace.rerun[0]):
                    namespace.input = namespace.rerun[0]  # also used as output since we don't set that
                    modifiedInput = True
                else:
                    namespace.output = namespace.rerun[0]
            else:
                self.error("Error: invalid argument for --rerun: %s" % namespace.rerun)
            if modifiedInput and dafPersist.Butler.getMapperClass(namespace.input) != mapperClass:
                self.error("Error: input directory specified by --rerun must have the same mapper as INPUT")
        else:
            namespace.rerun = None
        del namespace.rawRerun
        
        namespace.log.info("input=%s"  % (namespace.input,))
        namespace.log.info("calib=%s"  % (namespace.calib,))
        namespace.log.info("output=%s" % (namespace.output,))
        
        if "config" in namespace.show:
            namespace.config.saveToStream(sys.stdout, "config")

        namespace.butler = dafPersist.Butler(
            root = namespace.input,
            calibRoot = namespace.calib,
            outputRoot = namespace.output,
        )

        self._castDataIds(namespace)

        self._makeDataRefList(namespace)
        if not namespace.dataRefList:
            namespace.log.warn("No data found")
        
        if "data" in namespace.show:
            for dataRef in namespace.dataRefList:
                print "dataRef.dataId =", dataRef.dataId
        
        if "exit" in namespace.show:
            sys.exit(0)

        if namespace.debug:
            try:
                import debug
            except ImportError:
                sys.stderr.write("Warning: no 'debug' module found\n")
                namespace.debug = False

        if namespace.logdest:
            namespace.log.addDestination(namespace.logdest)
        del namespace.logdest
        
        if namespace.loglevel:
            permitted = ('DEBUG', 'INFO', 'WARN', 'FATAL')
            if namespace.loglevel.upper() in permitted:
                value = getattr(pexLog.Log, namespace.loglevel.upper())
            else:
                try:
                    value = int(namespace.loglevel)
                except ValueError:
                    self.error("log-level=%s not int or one of %s" % (namespace.loglevel, permitted))
            namespace.log.setThreshold(value)
        del namespace.loglevel
        
        namespace.config.validate()
        namespace.config.freeze()

        return namespace
    
    def _castDataIds(self, namespace):
        """Validate data IDs and cast them to the correct type
        """
        idKeyTypeDict = namespace.butler.getKeys(datasetType=namespace.datasetType, level=self._dataRefLevel)
        
        # convert data in namespace.dataIdList to proper types
        # this is done after constructing the butler, hence after parsing the command line,
        # because it takes a long time to construct a butler
        for dataDict in namespace.dataIdList:
            for key, strVal in dataDict.iteritems():
                try:
                    keyType = idKeyTypeDict[key]
                except KeyError:
                    validKeys = sorted(idKeyTypeDict.keys())
                    self.error("Unrecognized ID key %r; valid keys are: %s" % (key, validKeys))
                if keyType != str:
                    try:
                        castVal = keyType(strVal)
                    except Exception:
                        self.error("Cannot cast value %r to %s for ID key %r" % (strVal, keyType, key,))
                    dataDict[key] = castVal
    
    def _makeDataRefList(self, namespace):
        """Make namespace.dataRefList from namespace.dataIdList
        
        useful because butler.subset is quite limited in what it supports
        """
        namespace.dataRefList = []
        for dataId in namespace.dataIdList:
            dataRefList = list(namespace.butler.subset(
                datasetType = namespace.datasetType,
                level = self._dataRefLevel,
                dataId = dataId,
            ))
            # exclude nonexistent data (why doesn't subset support this?);
            # this is a recursive test, e.g. for the sake of "raw" data
            dataRefList = [dr for dr in dataRefList if dataExists(
                butler = namespace.butler,
                datasetType = namespace.datasetType,
                dataRef = dr,
            )]
            if not dataRefList:
                namespace.log.warn("No data found for dataId=%s" % (dataId,))
                continue
            namespace.dataRefList += dataRefList
        
    def _applyInitialOverrides(self, namespace):
        """Apply obs-package-specific and camera-specific config override files, if found
        
        Look in the package namespace.obs_pkg for files:
        - config/<task_name>.py
        - config/<camera_name>/<task_name>.py
        and load if found
        """
        obsPkgDir = eups.productDir(namespace.obsPkg)
        fileName = self._name + ".py"
        if not obsPkgDir:
            raise RuntimeError("Must set up %r" % (namespace.obsPkg,))
        for filePath in (
            os.path.join(obsPkgDir, "config", fileName),
            os.path.join(obsPkgDir, "config", namespace.camera, fileName),
        ):
            if os.path.exists(filePath):
                namespace.log.info("Loading config overrride file %r" % (filePath,))
                namespace.config.load(filePath)
            else:
                namespace.log.info("Config override file does not exist: %r" % (filePath,))
    
    def handleCamera(self, namespace):
        """Perform camera-specific operations before parsing the command line.
        
        @param[in] namespace: namespace object with the following fields:
            - camera: the camera name
            - config: the config passed to parse_args, with no overrides applied
            - obsPkg: the obs_ package for this camera
            - log: a pex_logging log
        """
        pass

    def convert_arg_line_to_args(self, arg_line):
        """Allow files of arguments referenced by @file to contain multiple values on each line
        """
        arg_line = arg_line.strip()
        if not arg_line or arg_line.startswith("#"):
            return
        for arg in shlex.split(arg_line, comments=True, posix=True):
            if not arg.strip():
                continue
            yield arg

class ConfigValueAction(argparse.Action):
    """argparse action callback to override config parameters using name=value pairs from the command line
    """
    def __call__(self, parser, namespace, values, option_string):
        """Override one or more config name value pairs
        """
        if namespace.config is None:
            return
        for nameValue in values:
            name, sep, valueStr = nameValue.partition("=")
            if not valueStr:
                parser.error("%s value %s must be in form name=value" % (option_string, nameValue))

            # see if setting the string value works; if not, try eval
            try:
                setDottedAttr(namespace.config, name, valueStr)
            except AttributeError:
                parser.error("no config field: %s" % (name,))
            except Exception:
                try:
                    value = eval(valueStr, {})
                except Exception:
                    parser.error("cannot parse %r as a value for %s" % (valueStr, name))
                try:
                    setDottedAttr(namespace.config, name, value)
                except Exception, e:
                    parser.error("cannot set config.%s=%r: %s" % (name, value, e))

class ConfigFileAction(argparse.Action):
    """argparse action to load config overrides from one or more files
    """
    def __call__(self, parser, namespace, values, option_string=None):
        """Load one or more files of config overrides
        """
        if namespace.config is None:
            return
        for configfile in values:
            try:
                namespace.config.load(configfile)
            except Exception, e:
                parser.error("cannot load config file %r: %s" % (configfile, e))
                

class IdValueAction(argparse.Action):
    """argparse action callback to add one data ID dict to namespace.dataIdList
    """
    def __call__(self, parser, namespace, values, option_string):
        """Parse --id data and append results to namespace.dataIdList
        
        The data format is:
        key1=value1_1[^value1_2[^value1_3...] key2=value2_1[^value2_2[^value2_3...]...

        The values (e.g. value1_1) may either be a string, or of the form "int..int" (e.g. "1..3")
        which is interpreted as "1^2^3" (inclusive, unlike a python range). So "0^2..4^7..9" is
        equivalent to "0^2^3^4^7^8^9".  You may also specify a stride: "1..5:2" is "1^3^5"
        
        The cross product is computed for keys with multiple values. For example:
            --id visit 1^2 ccd 1,1^2,2
        results in the following data ID dicts being appended to namespace.dataIdList:
            {"visit":1, "ccd":"1,1"}
            {"visit":2, "ccd":"1,1"}
            {"visit":1, "ccd":"2,2"}
            {"visit":2, "ccd":"2,2"}
        """
        if namespace.config is None:
            return
        idDict = dict()
        for nameValue in values:
            name, sep, valueStr = nameValue.partition("=")
            idDict[name] = []
            for v in valueStr.split("^"):
                mat = re.search(r"^(\d+)\.\.(\d+)(?::(\d+))?$", v)
                if mat:
                    v1 = int(mat.group(1))
                    v2 = int(mat.group(2))
                    v3 = mat.group(3); v3 = int(v3) if v3 else 1
                    for v in range(v1, v2 + 1, v3):
                        idDict[name].append(str(v))
                else:
                    idDict[name].append(v)

        keyList = idDict.keys()
        iterList = [idDict[key] for key in keyList]
        idDictList = [dict(zip(keyList, valList)) for valList in itertools.product(*iterList)]

        namespace.dataIdList += idDictList

class TraceLevelAction(argparse.Action):
    """argparse action to set trace level"""
    def __call__(self, parser, namespace, values, option_string):
        for componentLevel in values:
            component, sep, levelStr = componentLevel.partition("=")
            if not levelStr:
                parser.error("%s level %s must be in form component=level" % (option_string, componentLevel))
            try:
                level = int(levelStr)
            except Exception:
                parser.error("cannot parse %r as an integer level for %s" % (levelStr, component))
            pexLog.Trace.setVerbosity(component, level)

class DatasetArgument(object):
    """Specify that the dataset type should be a command-line option.

    Somewhat more heavyweight than just using, e.g., None as a signal, but
    provides the ability to have more informative help and a default.  Also
    more extensible in the future.

    @param[in] help: help string for the command-line option
    @param[in] default: default value; if None, then the option is required
    """
    def __init__(self,
            help="dataset type to process from input data repository",
            default=None):
        self.help = help
        self.default = default

    @property
    def required(self):
        return self.default is None

def setDottedAttr(item, name, value):
    """Like setattr, but accepts hierarchical names, e.g. foo.bar.baz
    """
    subitem = item
    subnameList = name.split(".")
    for subname in subnameList[:-1]:
        subitem = getattr(subitem, subname)
    setattr(subitem, subnameList[-1], value)

def getDottedAttr(item, name):
    """Like getattr, but accepts hierarchical names, e.g. foo.bar.baz
    """
    subitem = item
    for subname in name.split("."):
        subitem = getattr(subitem, subname)
    return subitem

def dataExists(butler, datasetType, dataRef):
    """Return True if data exists at the current level or any data exists at any level below
    """
    subDRList = dataRef.subItems()
    if subDRList:
        for subDR in subDRList:
            if dataExists(butler, datasetType, subDR):
                return True
        return False
    else:
        return butler.datasetExists(datasetType = datasetType, dataId = dataRef.dataId)
