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
import os.path
import shlex
import sys

import lsst.pex.logging as pexLog
import lsst.daf.persistence as dafPersist

__all__ = ["ArgumentParser"]

class ArgumentParser(argparse.ArgumentParser):
    """An argument parser for pipeline tasks that is based on argparse.ArgumentParser
    
    Users may wish to add additional arguments before calling parse_args.
    
    @notes
    * The need to specify camera name will go away in a few weeks once the repository format allows
      constructing a butler without knowing it.
    * I would prefer to check data ID keys and values as they are parsed,
      but the required information comes from the butler, so I have to construct a butler
      before I do this checking. Constructing a butler is slow, so I only want do it once,
      after parsing the command line.
    """
    def __init__(self,
        usage = "%(prog)s camera dataSource [options]",
        datasetType = "raw",
        dataRefLevel = None,
    **kwargs):
        """Construct an ArgumentParser
        
        @param usage: usage string (will probably go away after camera is no longer required)
        @param datasetType: dataset type appropriate to the task at hand;
            this affects which data ID keys are recognized.
        @param dataRefLevel: the level of the data references returned in dataRefList;
            None uses the data mapper's default, which is usually sensor.
            Warning: any value other than None is likely to be repository-specific.
        @param **kwargs: additional keyword arguments for argparse.ArgumentParser
        """
        self._datasetType = datasetType
        self._dataRefLevel = dataRefLevel
        argparse.ArgumentParser.__init__(self,
            usage = usage,
            fromfile_prefix_chars = '@',
            epilog = """Notes:
* --outpath is presently IGNORED; implementation is waiting for butler improvements
* The need to specify camera is temporary
* --config, --configfile, --id, --trace and @file may appear multiple times;
    all values are used, in order left to right
* @file reads command-line options from the specified file:
    * data may be distributed among multiple lines (e.g. one option per line)
    * data after # is treated as a comment and ignored
    * blank lines and lines starting with # are ignored
* To specify multiple values for an option, do not use = after the option name:
    * wrong: --configfile=foo bar
    * right: --configfile foo bar
""",
            formatter_class = argparse.RawDescriptionHelpFormatter,
        **kwargs)
        self.add_argument("camera", help="name of camera (e.g. lsstSim or suprimecam)")
        self.add_argument("dataPath", help="path to data repository")
        self.add_argument("--output", dest="outPath", help="output root directory")
        self.add_argument("--calib", dest="calibPath", help="calibration root directory")
        self.add_argument("--id", nargs="*", action=IdValueAction,
            help="data ID, e.g. --id visit=12345 ccd=1,2", metavar="KEY=VALUE1[^VALUE2[^VALUE3...]")
        self.add_argument("-c", "--config", nargs="*", action=ConfigValueAction,
            help="config override(s), e.g. -c foo=newfoo bar.baz=3", metavar="NAME=VALUE")
        self.add_argument("-C", "--configfile", dest="configFile", nargs="*", action=ConfigFileAction,
            help="config override file(s)")
        self.add_argument("-R", "--rerun", dest="rerun", default=os.getenv("USER", default="rerun"),
            help="rerun name")
        self.add_argument("-L", "--log-level", action=LogLevelAction, help="logging level")
        self.add_argument("-T", "--trace", nargs="*", action=TraceLevelAction,
            help="trace level for component", metavar="COMPONENT=LEVEL")
        self.add_argument("--debug", action="store_true", help="enable debugging output?")
        self.add_argument("--log", dest="logDest", help="logging destination")

    def parse_args(self, config, argv=None):
        """Parse arguments for a pipeline task

        @params config: config for the task being run
        @params argv: argv to parse; if None then sys.argv[1:] is used
        
        @return namespace: a struct containing many useful fields including:
        - config: the supplied config with all overrides applied
        - butler: a butler for the data
        - dataIdList: a list of data ID dicts
        - dataRefList: a list of butler data references
        - mapper: a mapper for the data
        - log: a log
        - an entry for each command-line argument, with a few exceptions such as configFile and logDest
        """
        if argv == None:
            argv = sys.argv[1:]

        _inNamespace = argparse.Namespace
        _inNamespace.config = config
        _inNamespace.dataIdList = []
        namespace = argparse.ArgumentParser.parse_args(self, args=argv, namespace=_inNamespace)
        del namespace.configFile
        del namespace.id
        
        if not os.path.isdir(namespace.dataPath):
            sys.stderr.write("Error: dataPath=%r not found\n" % (namespace.dataPath,))
            sys.exit(1)
        
        self._createMapper(namespace)
        butlerFactory = dafPersist.ButlerFactory(mapper = namespace.mapper)
        namespace.butler = butlerFactory.create()
        idKeyTypeDict = namespace.butler.getKeys(datasetType=self._datasetType, level=self._dataRefLevel)       
        
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

        namespace.dataRefList = [dataRef for dataId in namespace.dataIdList \
                                    for dataRef in namespace.butler.subset(
                                        datasetType = self._datasetType,
                                        level = self._dataRefLevel,
                                        **dataId)]

        if namespace.debug:
            try:
                import debug
            except ImportError:
                sys.stderr.write("Warning: no 'debug' module found\n")
                namespace.debug = False

        log = pexLog.Log.getDefaultLog()
        if namespace.logDest:
            log.addDestination(namespace.logDest)
        namespace.log = log
        del namespace.logDest

        return namespace

    def _createMapper(self, namespace):
        """Construct namespace.mapper based on namespace.camera, dataPath and calibPath.
        
        This is a temporary hack to set self._mapperClass; this will go away once the butler
        renders it unnecessary, and the user will no longer have to supply the camera name.
        """
        lowCamera = namespace.camera.lower()
        if lowCamera == "lsstsim":
            try:
                from lsst.obs.lsstSim import LsstSimMapper as Mapper
            except ImportError:
                self.error("Must setup obs_lsstSim to use lsstSim")
        elif lowCamera == "suprimecam":
            try:
                from lsst.obs.suprimecam import SuprimecamMapper as Mapper
            except ImportError:
                self.error("Must setup obs_suprimecam to use suprimecam")
        elif lowCamera == "cfht":
            try:
                from lsst.obs.cfht import CfhtMapper as Mapper
            except ImportError:
                self.error("Must setup obs_cfht to use CFHT")
        else:
            self.error("Unsupported camera: %s" % namespace.camera)
        namespace.mapper = Mapper(root=namespace.dataPath, calibRoot=namespace.calibPath)

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
        for nameValue in values:
            name, sep, valueStr = nameValue.partition("=")
            if not valueStr:
                parser.error("%s value %s must be in form name=value" % (option_string, nameValue))
            try:
                value = eval(valueStr, {})
            except Exception:
                parser.error("Cannot parse %r as a value for %s" % (valueStr, name))
            setattr(namespace.config, name, value)

class ConfigFileAction(argparse.Action):
    """argparse action to load config overrides from one or more files
    """
    def __call__(self, parser, namespace, values, option_string=None):
        """Load one or more files of config overrides
        """
        for configFile in values:
            namespace.config.load(configFile)

class IdValueAction(argparse.Action):
    """argparse action callback to add one data ID dict to namespace.dataIdList
    """
    def __call__(self, parser, namespace, values, option_string):
        """Parse --id data and append results to namespace.dataIdList
        
        The data format is:
        key1=value1_1[^value1_2[^value1_3...] key2=value2_1[^value2_2[^value2_3...]...
        
        The cross product is computed for keys with multiple values. For example:
            --id visit 1^2 ccd 1,1^2,2
        results in the following data ID dicts being appended to namespace.dataIdList:
            {"visit":1, "ccd":"1,1"}
            {"visit":2, "ccd":"1,1"}
            {"visit":1, "ccd":"2,2"}
            {"visit":2, "ccd":"2,2"}
        """
        idDict = dict()
        for nameValue in values:
            name, sep, valueStr = nameValue.partition("=")
            idDict[name] = valueStr.split("^")

        keyList = idDict.keys()
        iterList = [idDict[key] for key in keyList]
        idDictList = [dict(zip(keyList, valList)) for valList in itertools.product(*iterList)]

        namespace.dataIdList += idDictList

class LogLevelAction(argparse.Action):
    """argparse action to set log level"""
    def __call__(self, parser, namespace, value, option_string):
        permitted = ('DEBUG', 'INFO', 'WARN', 'FATAL')
        if value.upper() in permitted:
            value = getattr(pexLog.Log, value.upper())
        else:
            try:
                value = int(value)
            except ValueError:
                parser.error("Cannot parse %s a logging level %s" % (value, permitted))
        log = pexLog.getDefaultLog()
        log.setThreshold(value)

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
                parser.error("Cannot parse %r as an integer level for %s" % (levelStr, component))
            pexLog.Trace.setVerbosity(component, level)
