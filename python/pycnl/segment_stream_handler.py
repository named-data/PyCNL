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
This module defines the SegmentStream class which attaches to a Namespace node
to fetch and return child segment packets in order.
"""

import logging
from pyndn import Name
from pycnl.namespace import Namespace, NamespaceState

class SegmentStreamHandler(Namespace.Handler):
    def __init__(self, onSegment = None):
        super(SegmentStreamHandler, self).__init__()

        self._maxRetrievedSegmentNumber = -1
        self._finalSegmentNumber = None
        self._interestPipelineSize = 8
        self._initialInterestCount = 1
        # The dictionary key is the callback ID. The value is the onSegment function.
        self._onSegmentCallbacks = {}

        if onSegment != None:
            self.addOnSegment(onSegment)

    def addOnSegment(self, onSegment):
        """
        Add an onSegment callback. When a new segment is available, this calls
        onSegment as described below. Segments are supplied in order.

        :param onSegment: This calls
          onSegment(segmentStream, segmentNamespace, callbackId)
          where segmentStream is this SegmentStream, segmentNamespace is the Namespace
          where you can use segmentNamespace.getObject(), and callbackId is the
          callback ID returned by this method. You must check if
          segmentNamespace is None because after supplying the final segment, this
          calls onSegment(stream, None, callbackId) to signal the "end of stream".
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
        self._interestPipelineSize = interestPipelineSize

    def getInitialInterestCount(self):
        """
        Get the initial Interest count (as described in setInitialInterestCount).

        :return: The initial Interest count.
        :rtype: int
        """
        return self._initialInterestCount

    def setInitialInterestCount(self, initialInterestCount):
        """
        Set the number of initial Interests to send for segments. By default
          this just sends an Interest for the first segment and waits for the
          response before fetching more segments, but if you know the number of
          segments you can reduce latency by initially requesting more segments.
          (However, you should not use a number larger than the Interest
          pipeline size.)

        :param int initialInterestCount: The initial Interest count.
        :raises RuntimeError: If initialInterestCount is less than 1.
        """
        if initialInterestCount < 1:
            raise RuntimeError("The initial Interest count must be at least 1")
        self._initialInterestCount = initialInterestCount

    def _onNamespaceSet(self):
        self.namespace.addOnObjectNeeded(self._onObjectNeeded)
        self.namespace.addOnStateChanged(self._onStateChanged)

    def _onObjectNeeded(self, namespace, neededNamespace, id):
        """
        Start fetching segment Data packets and adding them as children of
        getNamespace(), calling any onSegment callbacks in order as the
        segments are received. Even though the segments supplied to onSegment
        are in order, note that children of the Namespace node are not
        necessarily added in order.
        """
        if namespace != neededNamespace:
            return False

        self._requestNewSegments(self._initialInterestCount)
        return True

    @staticmethod
    def debugGetRightmostLeaf(namespace):
        """
        Get the rightmost leaf of the given namespace. Use this temporarily to
        handle encrypted data packets where the name has the key name appended.

        :param Namespace namespace: The Namespace with the leaf node.
        :return: The leaf Namespace node.
        :rtype: Namespace
        """
        result = namespace
        while True:
            childComponents = result.getChildComponents()
            if len(childComponents) == 0:
                return result

            result = result[childComponents[-1]]

    def _onStateChanged(self, namespace, changedNamespace, state, callbackId):
        if not (len(changedNamespace.name) >= len(namespace.name) + 1 and
                state == NamespaceState.OBJECT_READY and
                changedNamespace.name[len(namespace.name)].isSegment()):
            # Not a segment, ignore.
            return

        metaInfo = changedNamespace.data.metaInfo
        if (metaInfo.getFinalBlockId().getValue().size() > 0 and
             metaInfo.getFinalBlockId().isSegment()):
            self._finalSegmentNumber = metaInfo.getFinalBlockId().toSegment()

        # Report as many segments as possible where the node already has content.
        while True:
            nextSegmentNumber = self._maxRetrievedSegmentNumber + 1
            nextSegment = self.debugGetRightmostLeaf(
              namespace[Name.Component.fromSegment(nextSegmentNumber)])
            if nextSegment.getObject() == None:
                break

            self._maxRetrievedSegmentNumber = nextSegmentNumber
            self._fireOnSegment(nextSegment)

            if (self._finalSegmentNumber != None and
                nextSegmentNumber == self._finalSegmentNumber):
                # Finished.
                self._fireOnSegment(None)
                return

        self._requestNewSegments(self._interestPipelineSize)

    def _requestNewSegments(self, maxRequestedSegments):
        if maxRequestedSegments < 1:
            maxRequestedSegments = 1

        childComponents = self.namespace.getChildComponents()
        # First, count how many are already requested and not received.
        nRequestedSegments = 0
        for component in childComponents:
            if not component.isSegment():
                # The namespace contains a child other than a segment. Ignore.
                continue

            child = self.namespace[component]
            # Debug: Check the leaf for content, but use the immediate child to
            # check if the Interest was expressed.
            if (self.debugGetRightmostLeaf(child).data == None and
                child.state >= NamespaceState.INTEREST_EXPRESSED):
                nRequestedSegments += 1
                if nRequestedSegments >= maxRequestedSegments:
                    # Already maxed out on requests.
                    break

        # Now find unrequested segment numbers and request.
        segmentNumber = self._maxRetrievedSegmentNumber
        while nRequestedSegments < maxRequestedSegments:
            segmentNumber += 1
            if (self._finalSegmentNumber != None and
                segmentNumber > self._finalSegmentNumber):
                break

            segment = self.namespace[Name.Component.fromSegment(segmentNumber)]
            if (self.debugGetRightmostLeaf(segment).data != None or
                segment.state >= NamespaceState.INTEREST_EXPRESSED):
                # Already got the data packet or already requested.
                continue

            nRequestedSegments += 1
            segment.objectNeeded()

    def _fireOnSegment(self, segmentNamespace):
        # Copy the keys before iterating since callbacks can change the list.
        for id in list(self._onSegmentCallbacks.keys()):
            # A callback on a previous pass may have removed this callback, so check.
            if id in self._onSegmentCallbacks.keys():
                try:
                    self._onSegmentCallbacks[id](self, segmentNamespace, id)
                except:
                    logging.exception("Error in onSegment")

    interestPipelineSize = property(getInterestPipelineSize, setInterestPipelineSize)
    initialInterestCount = property(getInitialInterestCount, setInitialInterestCount)