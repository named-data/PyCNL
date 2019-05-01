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
This registers with the local NFD to produce versioned generalized object test
data on demand from test_versioned_generalized_object_consumer (which must be
run separately).
"""

import time
import datetime
from pyndn import Name, Face, MetaInfo
from pyndn.util import Blob
from pyndn.util.common import Common
from pyndn.security import KeyChain
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

    # Use the system default key chain and certificate name to sign.
    keyChain = KeyChain()
    face.setCommandSigningInfo(keyChain, keyChain.getDefaultCertificateName())

    prefix = Namespace("/ndn/test/status", keyChain)

    dump("Register prefix", prefix.name)
    # Set the face and register to receive Interests.
    prefix.setFace(face,
      lambda prefixName: dump("Register failed for prefix", prefixName))

    handler = GeneralizedObjectHandler()
    # Each generalized object will have a 1000 millisecond freshness period.
    metaInfo = MetaInfo()
    metaInfo.setFreshnessPeriod(1000.0)

    # This is called when the library receives an Interest which is not
    # satisfied by Data already in the Namespace tree.
    def onObjectNeeded(namespace, neededNamespace, callbackId):
        if not (neededNamespace is prefix):
            # This is not the expected Namespace.
            return False

        # Make a version from the current time.
        versionNamespace = prefix[
          Name.Component.fromVersion(Common.getNowMilliseconds())]
        # The metaInfo has the freshness period.
        versionNamespace.setNewDataMetaInfo(metaInfo)
        dump("Producing the generalized object for", versionNamespace.name)
        handler.setObject(
          versionNamespace, Blob("Status as of " + str(datetime.datetime.now())),
          "text/html")
        return True

    prefix.addOnObjectNeeded(onObjectNeeded)

    while True:
        face.processEvents()
        # We need to sleep for a few milliseconds so we don't use 100% of the CPU.
        time.sleep(0.01)

main()
