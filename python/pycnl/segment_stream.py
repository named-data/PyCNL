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
This module defines the SegmentStream class which attached to a Namespace node
to fetch and return child segment packets in order.
"""

import logging
from pyndn import Name, Interest
from pyndn.util import ExponentialReExpress
from pycnl.namespace import Namespace
from pycnl.util.segment_store import SegmentStore

class SegmentStream(object):
    def __init__(self, namespace, face):
        """
        Create a SegmentStream object to attach to the given namespace and use
        the given face. You can add callbacks and set options, then you should
        call start().

        :param Namespace namespace: The Namespace node whose children are the
          names of segment Data packets.
        :param Face face: This calls face.expressInterest to fetch segments.
        """
        self._namespace = namespace
        self._face = face
        self._segmentStore = SegmentStore()
        self._didRequestFinalSegment = False
        self._finalSegmentNumber = None
        self._interestPipelineSize = 8
        # The dictionary key is the callback ID. The value is the onSegment function.
        self._onSegmentCallbacks = {}

        self._interestTemplate = Interest()
        self._interestTemplate.setInterestLifetimeMilliseconds(4000)

    def addOnSegment(self, onSegment):
        """
        Add an onSegment callback. When a new segment is is available, this calls
        onSegment(namespace, segment, callbackId) as described below. Segments
        are supplied in order.

        :param onSegment: This calls onSegment(stream, segment, callbackId)
          where stream is this SegmentStream, segment is the segment Data packet,
          and callbackId is the callback ID returned by this method. You must
          check if the segment value is None because after supplying the final
          segment, this calls onSegment(namespace, None, callbackId) to signal
          the "end of stream".
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        :type onComplete: function object
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
        self._expressInterest(self._namespace.getName(), self._interestTemplate)
        
    def _onData(self, interest, data):
        if not (len(data.name) == len(self._namespace.getName()) + 1 and
                data.name[-1].isSegment()):
            # Not a segment, ignore.
            return

        # TODO: Validate the Data packet.

        # Update the Namespace.
        self._namespace.getChild(data.name[-1])

        segmentNumber = data.name[-1].toSegment()
        self._segmentStore.storeData(segmentNumber, data)

        if (data.getMetaInfo().getFinalBlockId().getValue().size() > 0 and
             data.getMetaInfo().getFinalBlockId().isSegment()):
            self._finalSegmentNumber = data.getMetaInfo().getFinalBlockId().toSegment()

        # Retrieve as many segments as possible from the store.
        while True:
            result = self._segmentStore.maybeRetrieveNextEntry()
            if result == None:
                break

            (storeSegmentNumber, storeData) = result
            self._fireOnSegment(storeData)

            if (self._finalSegmentNumber != None and
                storeSegmentNumber == self._finalSegmentNumber):
                # Finished.
                self._fireOnSegment(None)
                return

        if self._finalSegmentNumber == None and not self._didRequestFinalSegment:
            self._didRequestFinalSegment = True
            # Try to determine the final segment now.
            # Copy the template to set the childSelector.
            interestTemplateCopy = Interest(self._interestTemplate)
            interestTemplateCopy.setChildSelector(1)
            self._expressInterest(self._namespace.getName(), interestTemplateCopy)

        # Request new segments.
        toRequest = self._segmentStore.requestSegmentNumbers(
          self._interestPipelineSize)
        for requestSegmentNumber in toRequest:
            if (self._finalSegmentNumber != None and
                requestSegmentNumber > self._finalSegmentNumber):
                continue

            name = Name(self._namespace.getName())
            name.appendSegment(requestSegmentNumber)
            self._expressInterest(name, self._interestTemplate)

    def _expressInterest(self, name, interestTemplate):
        # TODO: Supply the caller's timeout.
        def dump(*list):
            result = ""
            for element in list:
                result += (element if type(element) is str else str(element)) + " "
            print(result)

        self._face.expressInterest(
          name, interestTemplate, self._onData,
          ExponentialReExpress.makeOnTimeout(self._face, self._onData, None))

    def _fireOnSegment(self, segment):
        for id in self._onSegmentCallbacks:
            try:
                self._onSegmentCallbacks[id](self, segment, id)
            except:
                logging.exception("Error in onSegment")

    namespace = property(getNamespace)
    interestPipelineSize = property(getInterestPipelineSize, setInterestPipelineSize)
