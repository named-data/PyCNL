# -*- Mode:python; c-file-style:"gnu"; indent-tabs-mode:nil -*- */
#
# Copyright (C) 2016 Regents of the University of California.
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
This module defines the SegmentedContent class which assembles the contents of
child segment packets into a single block of memory.
"""

import logging
from pyndn.util import Blob
from pycnl.namespace import Namespace

class SegmentedContent(object):
    def __init__(self, segmentStream):
        """
        Create a SegmentedContent object to use the given segmentStream to
        assemble content. You can add callbacks and set options, then you
        should call segmentStream.start().

        :param Namespace namespace: The Namespace node whose children are the
          names of segment Data packets.
        :param Face face: This calls face.expressInterest to fetch segments.
        """
        self._segmentStream = segmentStream
        # The dictionary key is the callback ID. The value is the onContent function.
        self._onContentCallbacks = {}
        self._segments = []
        self._totalSize = 0

        self._segmentStream.addOnSegment(self._onSegment)

    def addOnContent(self, onContent):
        """
        Add an onContent callback. When all the segments are available, this
        calls onContent as described below.

        :param onContent: This calls onContent(handler, content, callbackId)
          where handler is this SegmentedContent, content is a Blob with the
          assembled segments as one memory block, and callbackId is the callback
          ID returned by this method.
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        :type onComplete: function object
        :return: The callback ID which you can use in removeCallback().
        :rtype: int
        """
        callbackId = Namespace.getNextCallbackId()
        self._onContentCallbacks[callbackId] = onContent
        return callbackId

    def removeCallback(self, callbackId):
        """
        Remove the callback with the given callbackId. If the callbackId isn't
        found, do nothing.

        :param int callbackId: The callback ID returned, for example, from
          addOnContent.
        """
        self._onContentCallbacks.pop(callbackId, None)

    def getSegmentStream(self):
        """
        Get the SegmentStream given to the constructor.

        :return: The SegmentStream.
        :rtype: SegmentStream.
        """
        return self._segmentStream

    def _onSegment(self, stream, segmentNamespace, id):
        if self._segments == None:
            # We already finished and called onContent. (We don't expect this.)
            return
          
        if segmentNamespace != None:
            self._segments.append(segmentNamespace.content)
            self._totalSize += segmentNamespace.content.size()
        else:
            # Finished. We don't need the callback anymore.
            stream.removeCallback(id)

            # Concatenate the segments.
            content = bytearray(self._totalSize)
            offset = 0
            for i in range(len(self._segments)):
                buffer = self._segments[i].toBuffer()
                content[offset:offset + len(buffer)] = buffer
                offset += len(buffer)
                # Free the memory.
                self._segments[i] = None
                
            self._segments = None
            self._fireOnContent(Blob(content, False))

    def _fireOnContent(self, content):
        # Copy the keys before iterating since callbacks can change the list.
        for id in list(self._onContentCallbacks.keys()):
            # A callback on a previous pass may have removed this callback, so check.
            if id in self._onContentCallbacks.keys():
                try:
                    self._onContentCallbacks[id](self, content, id)
                except:
                    logging.exception("Error in onContent")
