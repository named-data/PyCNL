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
This module defines the SegmentStream class which attaches to a Namespace node
to fetch and return child segment packets in order.
"""

import logging
import bisect
from pyndn import Name, Interest
from pycnl.namespace import Namespace

class SegmentStream(object):
    def __init__(self, namespace):
        """
        Create a SegmentStream object to attach to the given namespace. You can
        add callbacks and set options, then you should call start().

        :param Namespace namespace: The Namespace node whose children are the
          names of segment Data packets.
        """
        self._namespace = namespace
        self._maxRetrievedSegmentNumber = -1
        self._didRequestFinalSegment = False
        self._finalSegmentNumber = None
        self._interestPipelineSize = 8
        # The dictionary key is the callback ID. The value is the onSegment function.
        self._onSegmentCallbacks = {}

        self._namespace.addOnDataSet(self._onDataSet)

    def addOnSegment(self, onSegment):
        """
        Add an onSegment callback. When a new segment is available, this calls
        onSegment as described below. Segments are supplied in order.

        :param onSegment: This calls onSegment(stream, segment, callbackId)
          where stream is this SegmentStream, segment is the segment Data packet,
          and callbackId is the callback ID returned by this method. You must
          check if the segment value is None because after supplying the final
          segment, this calls onSegment(namespace, None, callbackId) to signal
          the "end of stream".
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        :type onSegment: function object
        :return: The callback ID which you can use in removeCallback().
        :rtype: int
        """
        callbackId = Namespace.getNextCallbackId()
        self._onSegmentCallbacks[callbackId] = onSegment
        return callbackId

    def removeCallback(self, callbackId):
        """
        Remove the callback with the given callbackId. If the callbackId isn't
        found, do nothing.

        :param int callbackId: The callback ID returned, for example, from
          addOnSegment.
        """
        self._onSegmentCallbacks.pop(callbackId, None)

    def getNamespace(self):
        """
        Get the Namespace object given to the constructor.

        :return: The Namespace object given to the constructor.
        :rtype: Namespace
        """
        return self._namespace

    def getInterestPipelineSize(self):
        """
        Get the number of outstanding interests which this maintains while
        fetching segments.

        :return: The Interest pipeline size.
        :rtype: int
        """
        return self._interestPipelineSize

    def setInterestPipelineSize(self, interestPipelineSize):
        """
        Set the number of outstanding interests which this maintains while
        fetching segments.

        :param int interestPipelineSize: The Interest pipeline size.
        :raises RuntimeError: If interestPipelineSize is less than 1.
        """
        if interestPipelineSize < 1:
            raise RuntimeError("The interestPipelineSize must be at least 1")
        return self._interestPipelineSize

    def start(self):
        """
        Start fetching segment Data packets and adding them as children of
        getNamespace(), calling any onSegment callbacks in order as the
        segments are received. Even though the segments supplied to onSegment
        are in order, note that children of the Namespace node are not
        necessarily added in order.
        """
        self._namespace.expressInterest()
        
    def _onDataSet(self, namespace, dataNamespace, callbackId):
        data = dataNamespace.data
        if not (len(data.name) == len(self._namespace.getName()) + 1 and
                data.name[-1].isSegment()):
            # Not a segment, ignore.
            # Debug: If this is the first call, we still need to request segments.
            return

        # TODO: Validate the Data packet.

        if (data.getMetaInfo().getFinalBlockId().getValue().size() > 0 and
             data.getMetaInfo().getFinalBlockId().isSegment()):
            self._finalSegmentNumber = data.getMetaInfo().getFinalBlockId().toSegment()

        # Retrieve as many segments as possible from the store.
        while True:
            nextSegmentNumber = self._maxRetrievedSegmentNumber + 1
            nextSegment = self._namespace[Name.Component.fromSegment(nextSegmentNumber)]
            if nextSegment.data == None:
                break

            self._maxRetrievedSegmentNumber = nextSegmentNumber
            self._fireOnSegment(nextSegment.data)

            if (self._finalSegmentNumber != None and
                nextSegmentNumber == self._finalSegmentNumber):
                # Finished.
                self._fireOnSegment(None)
                return

        if self._finalSegmentNumber == None and not self._didRequestFinalSegment:
            self._didRequestFinalSegment = True
            # Try to determine the final segment now.
            interestTemplate = Interest()
            interestTemplate.setInterestLifetimeMilliseconds(4000)
            interestTemplate.setChildSelector(1)
            self._namespace.expressInterest(interestTemplate)

        # Request new segments.
        childComponents = self._namespace.getChildComponents()
        # First, count how many are already requested and not received.
        nRequestedSegments = 0
        for component in childComponents:
            if not component.isSegment():
                # The namespace contains a child other than a segment. Ignore.
                continue

            child = self._namespace[component]
            if (child.data == None and
                  hasattr(child, '_debugSegmentStreamDidExpressInterest') and
                  child._debugSegmentStreamDidExpressInterest):
                nRequestedSegments += 1
                if nRequestedSegments >= self._interestPipelineSize:
                    # Already maxed out on requests.
                    break

        # Now find unrequested segment numbers and request.
        segmentNumber = self._maxRetrievedSegmentNumber
        while nRequestedSegments < self._interestPipelineSize:
            segmentNumber += 1
            if (self._finalSegmentNumber != None and
                segmentNumber > self._finalSegmentNumber):
                break

            segment = self._namespace[Name.Component.fromSegment(segmentNumber)]
            if (segment.data != None or
                (hasattr(segment, '_debugSegmentStreamDidExpressInterest') and
                  segment._debugSegmentStreamDidExpressInterest)):
                # Already got the data packet or already requested.
                continue

            nRequestedSegments += 1
            segment._debugSegmentStreamDidExpressInterest = True
            segment.expressInterest()

    def _fireOnSegment(self, segment):
        # Copy the keys before iterating since callbacks can change the list.
        for id in list(self._onSegmentCallbacks.keys()):
            # A callback on a previous pass may have removed this callback, so check.
            if id in self._onSegmentCallbacks.keys():
                try:
                    self._onSegmentCallbacks[id](self, segment, id)
                except:
                    logging.exception("Error in onSegment")

    namespace = property(getNamespace)
    interestPipelineSize = property(getInterestPipelineSize, setInterestPipelineSize)
