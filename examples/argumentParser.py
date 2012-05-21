#!/usr/bin/env python
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
"""Example showing use of the argument parser

@note
- to select data you must specify --id
- you may wish to display the config and data using --show config data
"""
import lsst.pex.config as pexConfig
import lsst.pipe.base as pipeBase

class ExampleConfig(pexConfig.Config):
    """Config for argument parser example
    """
    oneInt = pexConfig.Field(
        dtype = int,
        doc = "Example integer value",
        default = 1,
    )
    oneFloat = pexConfig.Field(
        dtype = float,
        doc = "Example float value",
        default = 3.14159265358979,
    )
    oneStr = pexConfig.Field(
        dtype = str,
        doc = "Example string value",
        default = "default value",
    )
    intList = pexConfig.ListField(
        dtype = int,
        doc = "example list of integers",
        default = [-1, 0, 1],
    )

parser = pipeBase.ArgumentParser(name="argumentParser")
config = ExampleConfig()
namespace = parser.parse_args(config=config)
print "namespace.dataIdList=%s" % (namespace.dataIdList,)
print "len(namespace.dataRefList)=%s" % (len(namespace.dataRefList),)
