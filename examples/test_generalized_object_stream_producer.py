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
This registers with the local NFD to produce a stream of generalized object test
data for test_generalized_object_stream consumer (which must be run separately).
"""

import time
from pyndn import Face
from pyndn.util import Blob
from pyndn.util.common import Common
from pyndn.security import KeyChain
from pycnl import Namespace
from pycnl.generalized_object import GeneralizedObjectStreamHandler

def dump(*list):
    result = ""
    for element in list:
        result += (element if type(element) is str else str(element)) + " "
    print(result)

def main():
    # The default Face will connect using a Unix socket, or to "localhost".
    face = Face()

    # Use the system default key chain and certificate name to sign.
    keyChain = KeyChain()
    face.setCommandSigningInfo(keyChain, keyChain.getDefaultCertificateName())

    publishIntervalMs = 1000.0
    stream = Namespace("/ndn/eb/stream/run/28/annotations", keyChain)
    handler = GeneralizedObjectStreamHandler()
    stream.setHandler(handler)

    dump("Register prefix", stream.name)
    # Set the face and register to receive Interests.
    stream.setFace(face,
      lambda prefixName: dump("Register failed for prefix", prefixName))

    # Loop, producing a new object every publishIntervalMs milliseconds (and
    # also calling processEvents()).
    previousPublishMs = 0
    while True:
        now = Common.getNowMilliseconds()
        if now >= previousPublishMs + publishIntervalMs:
            dump("Preparing data for sequence",
              handler.getProducedSequenceNumber() + 1)
            handler.addObject(
              Blob("Payload " + str(handler.getProducedSequenceNumber() + 1)),
              "application/json")

            previousPublishMs = now

        face.processEvents()
        # We need to sleep for a few milliseconds so we don't use 100% of the CPU.
        time.sleep(0.01)

main()
