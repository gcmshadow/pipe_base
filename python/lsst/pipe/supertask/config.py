#
# LSST Data Management System
# Copyright 2018 LSST Corporation.
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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the LSST License Statement and
# the GNU General Public License along with this program.  If not,
# see <http://www.lsstcorp.org/LegalNotices/>.
#
"""
Module defining config classes for SuperTask.
"""

from __future__ import absolute_import, division, print_function

__all__ = ["QuantumConfig", "InputDatasetConfig", "OutputDatasetConfig",
           "SuperTaskConfig"]

#--------------------------------
#  Imports of standard modules --
#--------------------------------

#-----------------------------
# Imports for other modules --
#-----------------------------
import lsst.pex.config as pexConfig

#----------------------------------
# Local non-exported definitions --
#----------------------------------

#------------------------
# Exported definitions --
#------------------------

class QuantumConfig(pexConfig.Config):
    """Configuration class which defines SuperTask quanta units.

    In addition to a list of dataUnit names this also includes optional list of
    SQL statements to be executed against Registry database. Exact meaning and
    format of SQL will be determined at later point.
    """
    units = pexConfig.ListField(dtype=str,
                                doc="list of DataUnits which define quantum")
    sql = pexConfig.ListField(dtype=str,
                              doc="sequence of SQL statements",
                              optional=True)


class InputDatasetConfig(pexConfig.Config):
    """Configuration class which defines SuperTask input dataset.

    Consists of DatasetType name and list of DataUnit names. SuperTasks
    typically define one or more input datasets.
    """
    name = pexConfig.Field(dtype=str,
                           doc="name of the DatasetType")
    units = pexConfig.ListField(dtype=str,
                                doc="list of DataUnits for this DatasetType")


class OutputDatasetConfig(pexConfig.Config):
    """Configuration class which defines SuperTask output dataset.

    Consists of DatasetType name and list of DataUnit names. SuperTasks
    typically define one or more output datasets.
    """
    name = pexConfig.Field(dtype=str,
                           doc="name of the DatasetType")
    units = pexConfig.ListField(dtype=str,
                                doc="list of DataUnits fior this DatasetType")


class SuperTaskConfig(pexConfig.Config):
    """Base class for all SuperTask configurations.

    This class defines fields that must be defined for every SuperTask.
    It will be used as a base class for all SuperTask configurations instead
    of `pex.config.Config`.
    """
    quantum = pexConfig.ConfigField(dtype=QuantumConfig,
                                    doc="configuration for SuperTask quantum")
