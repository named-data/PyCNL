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
This tests fetching a stream of generalized objects provided by
test_generalized_object_stream_producer (which must be running).
"""

import time
from pyndn import Interest, Face
from pycnl import Namespace
from pycnl.generalized_object import GeneralizedObjectStreamHandler

def dump(*list):
    result = ""
    for element in list:
        result += (element if type(element) is str else str(element)) + " "
    print(result)

def main():
    # Silence the warning from Interest wire encode.
    Interest.setDefaultCanBePrefix(True)

    # The default Face will connect using a Unix socket, or to "localhost".
    face = Face()

    stream = Namespace("/ndn/eb/stream/run/28/annotations")
    stream.setFace(face)

    def onNewObject(sequenceNumber, contentMetaInfo, objectNamespace):
        dump("Got generalized object, sequenceNumber", sequenceNumber,
             ", content-type", contentMetaInfo.getContentType(), ":",
             str(objectNamespace.obj))
    pipelineSize = 10
    stream.setHandler(
      GeneralizedObjectStreamHandler(pipelineSize, onNewObject)).objectNeeded()

    while True:
        face.processEvents()
        # We need to sleep for a few milliseconds so we don't use 100% of the CPU.
        time.sleep(0.01)

main()
