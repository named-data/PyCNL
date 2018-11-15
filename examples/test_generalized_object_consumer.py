# -*- Mode:python; c-file-style:"gnu"; indent-tabs-mode:nil -*- */
#
# Copyright (C) 2018 Regents of the University of California.
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
This tests fetching of generalized objects provided by
test_generalized_object_producer (which must be running).
"""

import time
from pyndn import Name, Face
from pycnl import Namespace
from pycnl.generalized_object import GeneralizedObjectHandler

def dump(*list):
    result = ""
    for element in list:
        result += (element if type(element) is str else str(element)) + " "
    print(result)

def main():
    # The default Face will connect using a Unix socket, or to "localhost".
    face = Face()

    prefix = Name("/ndn/stream_prefix/1")
    prefixNamespace = Namespace(prefix)
    prefixNamespace.setFace(face)

    enabled = [True]
    def onGeneralizedObject(contentMetaInfo, obj):
        dump("Got generalized object, content-type",
             contentMetaInfo.getContentType(), ":", str(obj))
        enabled[0] = False

    prefixNamespace.setHandler(GeneralizedObjectHandler(onGeneralizedObject)).objectNeeded()

    # Loop calling processEvents until a callback sets enabled[0] = False.
    while enabled[0]:
        face.processEvents()
        # We need to sleep for a few milliseconds so we don't use 100% of the CPU.
        time.sleep(0.01)

main()
