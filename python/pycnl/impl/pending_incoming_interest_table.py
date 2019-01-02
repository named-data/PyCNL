# -*- Mode:python; c-file-style:"gnu"; indent-tabs-mode:nil -*- */
#
# Copyright (C) 2018-2019 Regents of the University of California.
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
This module defines PendingImcomingInterestTable which is an internal class to
hold a list of Interests which OnInterest received but could not satisfy.
"""

import logging
from pyndn.util.common import Common

class PendingIncomingInterestTable(object):
    def __init__(self):
        self._table = []  # of Entry

    class Entry(object):
        """
        Create a PendingIncomingInterestTable.Entry and set the _timeoutTime
        based on the current time and the Interest lifetime.

        :param Interest interest: The Interest. This does not make a copy.
        :param Face face: The face from the OnInterest callback.
          If the Interest is satisfied later by a new data packet, we will send
          the Data packet to the face.
        """
        def __init__(self, interest, face):
            self._interest = interest
            self._face = face

            # Set up _timeoutTimeMilliseconds.
            if self._interest.getInterestLifetimeMilliseconds() >= 0.0:
              self._timeoutTimeMilliseconds = (Common.getNowMilliseconds() +
                self._interest.getInterestLifetimeMilliseconds())
            else:
              # No timeout.
              self._timeoutTimeMilliseconds = -1.0

        def getInterest(self):
            """
            Return the interest given to the constructor.
            """
            return self._interest

        def getFace(self):
            """
            Return the face given to the constructor.
            """
            return self._face

        def isTimedOut(self, nowMilliseconds):
            """
            Check if this Interest is timed out.

            :param float nowMilliseconds: The current time in milliseconds from
              Common.getNowMilliseconds.
            :return: True if this Interest is timed out, otherwise False.
            :rtype: bool
            """
            return (self._timeoutTimeMilliseconds >= 0.0 and
                    nowMilliseconds >= self._timeoutTimeMilliseconds)

    def add(self, interest, face):
        """
        Store an interest from an OnInterest callback in the internal pending
        interest table. Use satisfyInterests(data) to check if the Data packet
        satisfies any pending interest.

        :param Interest interest: The Interest for which we don't have a Data
          packet yet. You should not modify the interest after calling this.
        :param Face face: The Face from the OnInterest callback with the
          connection which received the Interest and to which satisfyInterests
          will send the Data packet.
        """
        self._table.append(PendingIncomingInterestTable.Entry(interest, face))

    def satisfyInterests(self, data):
        """
        Remove timed-out Interests, then for each pending Interest that the Data
        packet matches, send the Data packet through the face and remove the
        pending Interest.

        :param Data data: The Data packet to send if it satisfies an Interest.
        """
        # Go backwards through the list so we can erase entries.
        nowMilliseconds = Common.getNowMilliseconds()

        for i in range(len(self._table) - 1, -1, -1):
            pendingInterest = self._table[i]
            if pendingInterest.isTimedOut(nowMilliseconds):
                self._table.pop(i)
                continue

            # TODO: Use matchesData to match selectors?
            if pendingInterest.getInterest().matchesName(data.getName()):
                try:
                    # Send to the same face from the original call to the 
                    # OnInterest callback. wireEncode returns the cached
                    # encoding if available.
                    pendingInterest.getFace().send(data.wireEncode())
                except:
                    logging.exception("Error calling Face.send in satisfyInterests")

                # The pending interest is satisfied, so remove it.
                self._table.pop(i)
