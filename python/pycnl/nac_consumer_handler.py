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
This module defines the NacConsumerHandler class which uses a Name-based Access
Control Consumer to automatically decrypt Data packets which are attached to a
Namespace node.
"""

from pyndn.encrypt import Consumer

class NacConsumerHandler(object):
    """
    Create a NacConsumerHandler object to attach to the given Namespace. This
    holds an internal NAC Consumer with the given values. This uses the Face
    which must already be set for the Namespace (or one of its parents).
    """
    def __init__(self, namespace, keyChain, groupName, consumerName, database):
        # TODO: What is the right way to get access to the Face?
        face = namespace._getFace()
        self._consumer = Consumer(
          face, keyChain, groupName, consumerName, database)

