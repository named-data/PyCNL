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
from pyndn.util import ExponentialReExpress
from pycnl.namespace import Namespace

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
        self._segmentStore = SegmentStream._SegmentStore()
        self._didRequestFinalSegment = False
        self._finalSegmentNumber = None
        self._interestPipelineSize = 8
        # The dictionary key is the callback ID. The value is the onSegment function.
        self._onSegmentCallbacks = {}

        self._interestTemplate = Interest()
        self._interestTemplate.setInterestLifetimeMilliseconds(4000)

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
        # Copy the keys before iterating since callbacks can change the list.
        for id in self._onSegmentCallbacks.keys():
            # A callback on a previous pass may have removed this callback, so check.
            if id in list(self._onSegmentCallbacks.keys()):
                try:
                    self._onSegmentCallbacks[id](self, segment, id)
                except:
                    logging.exception("Error in onSegment")

    class _SegmentStore(object):
        def __init__(self):
            # The key is the segment number. The value is None if the segment number
            # is requested or the data if received.
            self._store = {}
            # The keys of _store in sorted order, kept in sync with _store.
            self._sortedStoreKeys = []
            self._maxRetrievedSegmentNumber = -1

        def storeData(self, segmentNumber, data):
            """
            Store the Data packet with the given segment number.
            requestSegmentNumbers will not return this requested segment number and
            maybeRetrieveNextEntry will return the Data packet when it is next.

            :param int segmentNumber: The segment number of the Data packet.
            :param Data data: The Data packet.
            """
            # We don't expect to try to store a segment that has already been
            # retrieved, but check anyway.
            if segmentNumber > self._maxRetrievedSegmentNumber:
                self._store[segmentNumber] = data
                # Keep _sortedStoreKeys synced with _store.
                if not segmentNumber in self._sortedStoreKeys:
                    bisect.insort(self._sortedStoreKeys, segmentNumber)

        def maybeRetrieveNextEntry(self):
            """
            If the min segment number is _maxRetrievedSegmentNumber + 1 and its
            value is not None, then delete from the store, return the segment number
            and Data packet, and update _maxRetrievedSegmentNumber. Otherwise return
            None.

            :return: (segmentNumber, data) if there is a next entry, otherwise None.
            :rtype: (int, Data)
            """
            if len(self._sortedStoreKeys) == 0:
                return None

            minSegmentNumber = self._sortedStoreKeys[0]
            if (self._store[minSegmentNumber] != None and
                 minSegmentNumber == self._maxRetrievedSegmentNumber + 1):
                data = self._store[minSegmentNumber]
                del self._store[minSegmentNumber]
                # Keep _sortedStoreKeys synced with _store.
                del self._sortedStoreKeys[0]

                self._maxRetrievedSegmentNumber += 1
                return (minSegmentNumber, data)
            else:
                return None

        def requestSegmentNumbers(self, totalRequestedSegments):
            """
            Return an array of the next segment numbers that need to be requested so
            that the total requested segments is totalRequestedSegments.  If a
            segment store value is None, it is already requested and is not
            returned.  If a segment number is returned, create an entry in the
            segment store with a value of None.

            :return: An array of segments number that should be requested. Note that
              these are not necessarily in order.
            :rtype: Array<int>
            """
            # First, count how many are already requested.
            nRequestedSegments = 0
            for segmentNumber in self._store:
                if self._store[segmentNumber] == None:
                    nRequestedSegments += 1
                    if nRequestedSegments >= totalRequestedSegments:
                        # Already maxed out on requests.
                        return []

            toRequest = []
            nextSegmentNumber = self._maxRetrievedSegmentNumber + 1
            for storeSegmentNumber in self._sortedStoreKeys:
                # Fill in the gap before the segment number in the store.
                while nextSegmentNumber < storeSegmentNumber:
                    toRequest.append(nextSegmentNumber)
                    nextSegmentNumber += 1
                    nRequestedSegments += 1
                    if nRequestedSegments >= totalRequestedSegments:
                        break
                if nRequestedSegments >= totalRequestedSegments:
                    break

                nextSegmentNumber = storeSegmentNumber + 1

            # We already filled in the gaps for the segments in the store. Continue
            # after the last.
            while nRequestedSegments < totalRequestedSegments:
                toRequest.append(nextSegmentNumber)
                nextSegmentNumber += 1
                nRequestedSegments += 1

            # Mark the new segment numbers as requested.
            for segmentNumber in toRequest:
                self._store[segmentNumber] = None
                # Keep _sortedStoreKeys synced with _store.
                bisect.insort(self._sortedStoreKeys, segmentNumber)

            return toRequest

    namespace = property(getNamespace)
    interestPipelineSize = property(getInterestPipelineSize, setInterestPipelineSize)
