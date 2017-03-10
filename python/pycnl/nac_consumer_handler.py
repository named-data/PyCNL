# -*- Mode:python; c-file-style:"gnu"; indent-tabs-mode:nil -*- */
#
# Copyright (C) 2016-2017 Regents of the University of California.
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

import logging
from pyndn.encrypt import Consumer

class NacConsumerHandler(object):
    """
    Create a NacConsumerHandler object to attach to the given Namespace. This
    holds an internal NAC Consumer with the given values. This uses the Face
    which must already be set for the Namespace (or one of its parents).

    :param Namespace namespace: The Namespace node whose content is transformed
      by decrypting it.
    :param KeyChain keyChain: The keyChain used to verify data packets.
    :param Name groupName: The reading group name that the consumer belongs to.
      This makes a copy of the Name.
    :param Name consumerName: The identity of the consumer. This makes a copy of
      the Name.
    :param ConsumerDb database: The ConsumerDb database for storing decryption
      keys.
    """
    def __init__(self, namespace, keyChain, groupName, consumerName, database):
        # TODO: What is the right way to get access to the Face?
        face = namespace._getFace()
        self._consumer = Consumer(
          face, keyChain, groupName, consumerName, database)

        # TODO: Use a way to set the callback which is better than setting the member.
        namespace._transformContent = self._transformContent

    def addDecryptionKey(self, keyName, keyBlob):
        """
        Add a new decryption key with keyName and keyBlob to the database given
        to the constructor.

        :param Name keyName: The key name.
        :param Blob keyBlob: The encoded key.
        :raises ConsumerDb.Error: If a key with the same keyName already exists
          in the database, or other database error.
        :raises RuntimeError: if the consumer name is not a prefix of the key name.
        """
        self._consumer.addDecryptionKey(keyName, keyBlob)

    def _transformContent(self, data, onContentTransformed):
        """
        This is the TransformContent callback to use the Consumer to decrypt
        data and call onContentTransformed as described below.

        :param Data data: The Data packet with the content to decrypt.
        :param onContentTransformed: This calls
          onContentTransformed(data, plainText) where data is the given Data,
          and plainText is the decrypted content Blob.
        :type onContentTransformed: function object
        """
        # TODO: Use Namespace mechanisms to verify the Data packet.

        def onPlainText(plainText):
            try:
                onContentTransformed(data, plainText)
            except:
                logging.exception("Error in onContentTransformed")
        # TODO: TransformContent should take an OnError to use here.
        def onError(code, message):
            logging.getLogger(__name__).error(
              "consume error " + repr(code) + ": " + message)
        # TODO: Update the Consumer class so we don't call a private method.
        self._consumer._decryptContent(data, onPlainText, onError)
