# -*- Mode:python; c-file-style:"gnu"; indent-tabs-mode:nil -*- */
#
# Copyright (C) 2016-2018 Regents of the University of California.
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
This module defines the SegmentedObjectHandler class which extends
SegmentStreamHandler and assembles the contents of child segments into a single
block of memory.
"""

from pyndn import Name, Data, DigestSha256Signature
from pyndn.util import Blob
from pycnl.namespace import Namespace
from pycnl.segment_stream_handler import SegmentStreamHandler

class SegmentedObjectHandler(SegmentStreamHandler):
    """
    Create a SegmentedObjectHandler with the optional onSegmentedObject callback.

    :param onSegmentedObject: (optional) If not None, this calls
      addOnSegmentedObject(onSegmentedObject). You may also call
      addOnSegmentedObject directly.
    :type onSegment: function object
    """
    def __init__(self, onSegmentedObject = None):
        super(SegmentedObjectHandler, self).__init__(self._onSegment)

        self._segments = []
        self._totalSize = 0
        # The dictionary key is the callback ID. The value is the OnSegmentedObject function.
        self._onSegmentedObjectCallbacks = {}
        self._maxSegmentPayloadLength = 8192

        if onSegmentedObject != None:
            self.addOnSegmentedObject(onSegmentedObject)

    def addOnSegmentedObject(self, onSegmentedObject):
        """
        Add an OnSegmentedObject callback. When the child segments are assembled
        into a single block of memory, this calls onSegmentedObject as described
        below.

        :param onSegmentedObject: This calls onSegmentedObject(object) where
          object is the object that was assembled from the segment contents and
          deserialized.
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        :type onSegment: function object
        :return: The callback ID which you can use in removeCallback().
        :rtype: int
        """
        callbackId = Namespace.getNextCallbackId()
        self._onSegmentedObjectCallbacks[callbackId] = onSegmentedObject
        return callbackId

    def removeCallback(self, callbackId):
        """
        Remove the callback with the given callbackId. If the callbackId isn't
        found, do nothing.

        :param int callbackId: The callback ID returned, for example, from
          addOnSegmentedObject.
        """
        self._onSegmentedObjectCallbacks.pop(callbackId, None)

    def getMaxSegmentPayloadLength(self):
        """
        Get the maximum length of the payload of one segment, used to split a
        larger payload into segments.

        :return: The maximum payload length.
        :rtype: int
        """
        return self._maxSegmentPayloadLength

    def setMaxSegmentPayloadLength(self, maxSegmentPayloadLength):
        """
        Set the maximum length of the payload of one segment, used to split a
        larger payload into segments.

        :param int maxSegmentPayloadLength: The maximum payload length.
        """
        if maxSegmentPayloadLength < 1:
            raise RuntimeError("The maximum segment payload length must be at least 1")
        self._maxSegmentPayloadLength = maxSegmentPayloadLength

    def setObject(self, namespace, obj, useSignatureManifest = False):
        """
        Segment the object and create child segment packets of the given Namespace.

        :param Namespace namespace: The Namespace to append segment packets to.
          This ignores the Namespace from setNamespace().
        :param Blob obj: The object to segment.
        :param bool useSignatureManifest: (optional) If True, only use a
          DigestSha256Signature on the segment packets and create a signed
          _manifest packet as a child of the given Namespace. If omitted or
          False, sign each segment packet individually.
        """
        keyChain = namespace._getKeyChain()
        if keyChain == None:
            raise RuntimeError("SegmentedObjectHandler.setObject: There is no KeyChain")

        # Get the final block ID.
        finalSegment = 0
        # Instead of a brute calculation, imitate the loop we will use below.
        segment = 0
        offset = 0
        while offset < obj.size():
            finalSegment = segment
            segment += 1
            offset += self._maxSegmentPayloadLength
        finalBlockId = Name().appendSegment(finalSegment)[0]

        SHA256_DIGEST_SIZE = 32
        if useSignatureManifest:
            # Get ready to save the segment payload digests.
            manifestContent = bytearray((finalSegment + 1) * SHA256_DIGEST_SIZE)

            # Use a DigestSha256Signature with all zeros.
            digestSignature = DigestSha256Signature()
            digestSignature.setSignature(Blob(bytearray(SHA256_DIGEST_SIZE)))

        segment = 0
        offset = 0
        while offset < obj.size():
            payloadLength = self._maxSegmentPayloadLength
            if offset + payloadLength > obj.size():
                payloadLength = obj.size() - offset

            # Make the Data packet.
            segmentNamespace = namespace[Name.Component.fromSegment(segment)]
            data = Data(segmentNamespace.getName())
            data.getMetaInfo().setFinalBlockId(finalBlockId)
            data.setContent(obj.toBytes()[offset:offset + payloadLength])

            if useSignatureManifest:
                data.setSignature(digestSignature)

                # Append the implicit digest to the manifestContent.
                implicitDigest = data.getFullName()[-1].getValue()
                digestOffset = segment * SHA256_DIGEST_SIZE
                manifestContent[digestOffset:digestOffset + SHA256_DIGEST_SIZE] = \
                  implicitDigest.toBytes()[:]
            else:
                keyChain.sign(data)

            segmentNamespace.setData(data)

            segment += 1
            offset += self._maxSegmentPayloadLength

        if useSignatureManifest:
            # Create the _manifest data packet.
            namespace[self.NAME_COMPONENT_MANIFEST].serializeObject(
              Blob(manifestContent))

        # TODO: Do this in a canSerialize callback from Namespace.serializeObject?
        nameSpace._setObject(obj)

    def _onSegment(self, segmentNamespace):
        if self._segments == None:
            # We already finished and called onContent. (We don't expect this.)
            return
          
        if segmentNamespace != None:
            self._segments.append(segmentNamespace.getObject())
            self._totalSize += segmentNamespace.getObject().size()
        else:
            # Concatenate the segments.
            content = bytearray(self._totalSize)
            offset = 0
            for i in range(len(self._segments)):
                buffer = self._segments[i].toBuffer()
                content[offset:offset + len(buffer)] = buffer
                offset += len(buffer)
                # Free the memory.
                self._segments[i] = None
                
            # Free memory.
            self._segments = None

            # Deserialize and fire the onSegmentedObject callbacks when done.
            self.namespace._deserialize(
              Blob(content, False), self._fireOnSegmentedObject)

    def _fireOnSegmentedObject(self, obj):
        # Copy the keys before iterating since callbacks can change the list.
        for id in list(self._onSegmentedObjectCallbacks.keys()):
            # A callback on a previous pass may have removed this callback, so check.
            if id in self._onSegmentedObjectCallbacks.keys():
                try:
                    self._onSegmentedObjectCallbacks[id](obj)
                except:
                    logging.exception("Error in onSegmentedObject")

    NAME_COMPONENT_MANIFEST = Name.Component("_manifest")

    maxSegmentPayloadLength = property(getMaxSegmentPayloadLength, setMaxSegmentPayloadLength)
