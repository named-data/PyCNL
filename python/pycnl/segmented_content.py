# -*- Mode:python; c-file-style:"gnu"; indent-tabs-mode:nil -*- */
#
# Copyright (C) 2016-2017 Regents of the University of California.
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

from pyndn.util import Blob
from pycnl.segment_stream import SegmentStream

class SegmentedContent(object):
    def __init__(self, segmentStreamOrNamespace):
        """
        Create a SegmentedContent object to use a SegmentStream to assemble
        content. You should use getNamespace().addOnContentSet to add the
        callback which is called when the content is complete. Then you should
        call start().

        :param segmentStreamOrNamespace: A SegmentStream where its
          Namespace is a node whose children are the names of segment Data
          packets. Alternatively, if this is a Namespace object, then use it to
          create a SegmentStream which you can access with getSegmentStream().
        :type segmentStreamOrNamespace: SegmentStream or Namespace
        """
        if isinstance(segmentStreamOrNamespace, SegmentStream):
            self._segmentStream = segmentStreamOrNamespace
        else:
            self._segmentStream = SegmentStream(segmentStreamOrNamespace)

        self._segments = []
        self._totalSize = 0

        self._segmentStream.addOnSegment(self._onSegment)

    def getSegmentStream(self):
        """
        Get the SegmentStream given to the constructor.

        :return: The SegmentStream.
        :rtype: SegmentStream.
        """
        return self._segmentStream

    def getNamespace(self):
        """
        Get the Namespace object for this handler.

        :return: The Namespace object for this handler.
        :rtype: Namespace
        """
        return self._segmentStream.getNamespace()

    def start(self):
        """
        Start fetching segment Data packets. When done, the library will call
        the callback given to getNamespace().addOnContentSet .
        """
        self._segmentStream.start()

    def _onSegment(self, segmentStream, segmentNamespace, callbackId):
        if self._segments == None:
            # We already finished and called onContent. (We don't expect this.)
            return
          
        if segmentNamespace != None:
            self._segments.append(segmentNamespace.content)
            self._totalSize += segmentNamespace.content.size()
        else:
            # Finished. We don't need the callback anymore.
            segmentStream.removeCallback(callbackId)

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

            # Debug: Fix this hack. How can we attach content to a namespace
            # node which has no associated Data packet? Who is authorized to do
            # so?
            self._segmentStream.namespace._onContentTransformed(
              None, Blob(content, False))
