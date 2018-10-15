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

"""
This module defines the SegmentedObjectHandler class which assembles the
contents of child segment packets into a single block of memory.
"""

from pyndn.util import Blob
from pycnl.namespace import NamespaceState
from pycnl.segment_stream_handler import SegmentStreamHandler

class SegmentedObjectHandler(SegmentStreamHandler):
    def __init__(self, onSegmentedObject = None):
        super(SegmentedObjectHandler, self).__init__(self._onSegment)

        self._segments = []
        self._totalSize = 0
        self._onSegmentedObject = onSegmentedObject

    def _onSegment(self, segmentNamespace, callbackId):
        if self._segments == None:
            # We already finished and called onContent. (We don't expect this.)
            return
          
        if segmentNamespace != None:
            self._segments.append(segmentNamespace.getObject())
            self._totalSize += segmentNamespace.getObject().size()
        else:
            # Finished. We don't need the callback anymore.
            self.removeCallback(callbackId)

            # Concatenate the segments.
            content = bytearray(self._totalSize)
            offset = 0
            for i in range(len(self._segments)):
                buffer = self._segments[i].toBuffer()
                content[offset:offset + len(buffer)] = buffer
                offset += len(buffer)
                # Free the memory.
                self._segments[i] = None
                
            # Free memory.
            self._segments = None

            contentBlob = Blob(content, False)
            # Debug: Call self.namespace.setObject().
            self.namespace._object = contentBlob
            self.namespace._setState(NamespaceState.OBJECT_READY)

            if self._onSegmentedObject != None:
                self._onSegmentedObject(self, contentBlob)
