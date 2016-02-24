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
This module defines the SegmentStore class which stores segments until they are
retrieved in order starting with segment 0.
"""

import bisect

class SegmentStore(object):
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
