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
This module defines the SegmentStream class which attaches to a Namespace node
to fetch and return child segment packets in order.
"""

import logging
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

        self._namespace.addOnContentSet(self._onContentSet)

    def addOnSegment(self, onSegment):
        """
        Add an onSegment callback. When a new segment is available, this calls
        onSegment as described below. Segments are supplied in order.

        :param onSegment: This calls
          onSegment(segmentStream, segmentNamespace, callbackId)
          where segmentStream is this SegmentStream, segmentNamespace is the Namespace
          where you can use segmentNamespace.content, and callbackId is the
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
        self._interestPipelineSize = interestPipelineSize

    def start(self):
        """
        Start fetching segment Data packets and adding them as children of
        getNamespace(), calling any onSegment callbacks in order as the
        segments are received. Even though the segments supplied to onSegment
        are in order, note that children of the Namespace node are not
        necessarily added in order.
        """
        self._requestNewSegments()

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

    def _onContentSet(self, namespace, contentNamespace, callbackId):
        if not (len(contentNamespace.name) >= len(self._namespace.name) + 1 and
                contentNamespace.name[len(self._namespace.name)].isSegment()):
            # Not a segment, ignore.
            return

        # TODO: Use the Namspace mechanism to validate the Data packet.

        metaInfo = contentNamespace.data.metaInfo
        if (metaInfo.getFinalBlockId().getValue().size() > 0 and
             metaInfo.getFinalBlockId().isSegment()):
            self._finalSegmentNumber = metaInfo.getFinalBlockId().toSegment()

        # Report as many segments as possible where the node already has content.
        while True:
            nextSegmentNumber = self._maxRetrievedSegmentNumber + 1
            nextSegment = self.debugGetRightmostLeaf(
              self._namespace[Name.Component.fromSegment(nextSegmentNumber)])
            if nextSegment.content.isNull():
                break

            self._maxRetrievedSegmentNumber = nextSegmentNumber
            self._fireOnSegment(nextSegment)

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

        self._requestNewSegments()

    def _requestNewSegments(self):
        childComponents = self._namespace.getChildComponents()
        # First, count how many are already requested and not received.
        nRequestedSegments = 0
        for component in childComponents:
            if not component.isSegment():
                # The namespace contains a child other than a segment. Ignore.
                continue

            child = self._namespace[component]
            # Debug: Check the leaf for content, but use the immediate child
            # for _debugSegmentStreamDidExpressInterest.
            if (self.debugGetRightmostLeaf(child).content.isNull() and
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
            if (not self.debugGetRightmostLeaf(segment).content.isNull() or
                (hasattr(segment, '_debugSegmentStreamDidExpressInterest') and
                  segment._debugSegmentStreamDidExpressInterest)):
                # Already got the data packet or already requested.
                continue

            nRequestedSegments += 1
            segment._debugSegmentStreamDidExpressInterest = True
            segment.expressInterest()

    def _fireOnSegment(self, segmentNamespace):
        # Copy the keys before iterating since callbacks can change the list.
        for id in list(self._onSegmentCallbacks.keys()):
            # A callback on a previous pass may have removed this callback, so check.
            if id in self._onSegmentCallbacks.keys():
                try:
                    self._onSegmentCallbacks[id](self, segmentNamespace, id)
                except:
                    logging.exception("Error in onSegment")

    namespace = property(getNamespace)
    interestPipelineSize = property(getInterestPipelineSize, setInterestPipelineSize)
