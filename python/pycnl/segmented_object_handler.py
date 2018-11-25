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
from pycnl.namespace import Namespace
from pycnl.segment_stream_handler import SegmentStreamHandler

class SegmentedObjectHandler(SegmentStreamHandler):
    """
    Create a SegmentedObjectHandler with the optional onSegmentedObject callback.

    :param onSegmentedObject: (optional) If not None, this calls
      addOnSegmentedObject(onSegmentedObject). You may also call
      addOnSegmentedObject directly.
    :type onSegment: function object
    """
    def __init__(self, onSegmentedObject = None):
        super(SegmentedObjectHandler, self).__init__(self._onSegment)

        self._segments = []
        self._totalSize = 0
        # The dictionary key is the callback ID. The value is the OnSegmentedObject function.
        self._onSegmentedObjectCallbacks = {}

        if onSegmentedObject != None:
            self.addOnSegmentedObject(onSegmentedObject)

    def addOnSegmentedObject(self, onSegmentedObject):
        """
        Add an OnSegmentedObject callback. When the child segments are assembled
        into a single block of memory, this calls onSegmentedObject as described
        below.

        :param onSegmentedObject: This calls onSegmentedObject(object) where
          object is the object that was assembled from the segment contents and
          deserialized.
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        :type onSegment: function object
        :return: The callback ID which you can use in removeCallback().
        :rtype: int
        """
        callbackId = Namespace.getNextCallbackId()
        self._onSegmentedObjectCallbacks[callbackId] = onSegmentedObject
        return callbackId

    def removeCallback(self, callbackId):
        """
        Remove the callback with the given callbackId. If the callbackId isn't
        found, do nothing.

        :param int callbackId: The callback ID returned, for example, from
          addOnSegmentedObject.
        """
        self._onSegmentedObjectCallbacks.pop(callbackId, None)

    def _onSegment(self, segmentNamespace):
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

            # Deserialize and fire the onSegmentedObject callbacks when done.
            self.namespace._deserialize(
              Blob(content, False), self._fireOnSegmentedObject)

    def _fireOnSegmentedObject(self, obj):
        # Copy the keys before iterating since callbacks can change the list.
        for id in list(self._onSegmentedObjectCallbacks.keys()):
            # A callback on a previous pass may have removed this callback, so check.
            if id in self._onSegmentedObjectCallbacks.keys():
                try:
                    self._onSegmentedObjectCallbacks[id](obj)
                except:
                    logging.exception("Error in onSegmentedObject")
