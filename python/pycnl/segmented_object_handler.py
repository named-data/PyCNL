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
This module defines the SegmentedObjectHandler class which extends
SegmentStreamHandler and assembles the contents of child segments into a single
block of memory.
"""

from pyndn.util import Blob
from pycnl.namespace import NamespaceState
from pycnl.segment_stream_handler import SegmentStreamHandler

class SegmentedObjectHandler(SegmentStreamHandler):
    """
    Create a SegmentedObjectHandler with the optional onSegmentedObject callback.

    :param onSegmentedObject: (optional) When the child segments are assembled
      into a single block of memory, this calls onSegment(handler, contentBlob)
      where handler is this SegmentedObjectHandler and contentBlob is the Blob
      assembled from the contents. If you don't supply an onSegmentedObject
      callback here, you can call addOnStateChanged on the Namespace object to
      which this is attached and listen for the OBJECT_READY state.
    :type onSegment: function object
    """
    def __init__(self, onSegmentedObject = None):
        super(SegmentedObjectHandler, self).__init__(self._onSegment)

        self._segments = []
        self._totalSize = 0
        self._onSegmentedObject = onSegmentedObject

    def _onSegment(self, handler, segmentNamespace, callbackId):
        if self._segments == None:
            # We already finished and called onContent. (We don't expect this.)
            return
          
        if segmentNamespace != None:
            self._segments.append(segmentNamespace.getObject())
            self._totalSize += segmentNamespace.getObject().size()
        else:
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
            self.namespace.setObject(contentBlob)

            if self._onSegmentedObject != None:
                self._onSegmentedObject(self, contentBlob)
