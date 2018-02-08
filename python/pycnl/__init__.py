# -*- Mode:python; c-file-style:"gnu"; indent-tabs-mode:nil -*- */
#
# Copyright (C) 2016-2018 Regents of the University of California.
# Author: Jeff Thompson <jefft0@remap.ucla.edu>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# A copy of the GNU Lesser General Public License is in the file COPYING.

from pycnl import nac_consumer_handler, namespace, segment_stream_handler
from pycnl import segmented_object_handler
__all__ = ['nac_consumer_handler', 'namespace', 'segment_stream_handler',
           'segmented_object_handler']

import sys as _sys

try:
    from pycnl.nac_consumer_handler import *
    from pycnl.namespace import *
    from pycnl.segment_stream_handler import *
    from pycnl.segmented_object_handler import *
except ImportError:
    del _sys.modules[__name__]
    raise
