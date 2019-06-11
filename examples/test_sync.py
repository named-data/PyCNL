# -*- Mode:python; c-file-style:"gnu"; indent-tabs-mode:nil -*- */
#
# Copyright (C) 2019 Regents of the University of California.
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
This registers with the local NFD to test sync functionality.
"""

import sys
import time
from pyndn import Name
from pyndn import Interest
from pyndn import Face
from pyndn.security import KeyChain
from pycnl import Namespace, NamespaceState
from pyndn.util.common import Common

def dump(*list):
    result = ""
    for element in list:
        result += (element if type(element) is str else str(element)) + " "
    print(result)

def main():
    # Silence the warning from Interest wire encode.
    Interest.setDefaultCanBePrefix(True)

    if sys.version_info[0] <= 2:
        userName = raw_input("Enter your user name (e.g. \"a\" or \"b\"): ")
    else:
        userName = input("Enter your user name (e.g. \"a\" or \"b\"): ")
    if userName == "":
        dump("You must enter a user name")
        return

    # The default Face will connect using a Unix socket, or to "localhost".
    face = Face()

    # Use the system default key chain and certificate name to sign.
    keyChain = KeyChain()
    face.setCommandSigningInfo(keyChain, keyChain.getDefaultCertificateName())

    applicationPrefix = Namespace(Name("/test/app"), keyChain)
    applicationPrefix.setFace(face,
      lambda prefix: dump("Register failed for prefix", prefix))
    applicationPrefix.enableSync()

    userPrefix = applicationPrefix[Name.Component(userName)]

    def onStateChanged(nameSpace, changedNamespace, state, callbackId):
        if (state == NamespaceState.NAME_EXISTS and
             not userPrefix.name.isPrefixOf(changedNamespace.name)):
            dump("Received", changedNamespace.name.toUri())

    applicationPrefix.addOnStateChanged(onStateChanged)

    publishIntervalMs = 1000.0
    component = Name("/%00").get(0)

    # Loop, producing a new name every publishIntervalMs milliseconds (and also
    # calling processEvents()).
    previousPublishMs = 0.0
    while True:
        now = Common.getNowMilliseconds()
        if now >= previousPublishMs + publishIntervalMs:
            # If userName is "a", this makes /test/app/a/%00, /test/app/a/%01, etc.
            newNamespace = userPrefix[component]
            dump("Publish", newNamespace.name.toUri())
            component = component.getSuccessor()

            previousPublishMs = now

        face.processEvents()
        # We need to sleep for a few milliseconds so we don't use 100% of the CPU.
        time.sleep(0.01)

main()
