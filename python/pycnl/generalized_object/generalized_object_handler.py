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
This module defines the GeneralizedObjectHandler class which extends
Namespace.Handler and attaches to a Namespace node to fetch the _meta packet
for a generalized object and, if necessary, assemble the contents of segment
packets into a single block of memory.
"""

import logging
from pyndn import Name
from pyndn.util.common import Common
from pycnl.namespace import Namespace, NamespaceState
from pycnl.segmented_object_handler import SegmentedObjectHandler
from pycnl.generalized_object.content_meta_info import ContentMetaInfo

class GeneralizedObjectHandler(Namespace.Handler):
    """
    Create a GeneralizedObjectHandler with the optional onGeneralizedObject
    callback.

    :param onGeneralizedObject: (optional) When the ContentMetaInfo is received
      and the hasSegments is False, this calls
      onGeneralizedObject(contentMetaInfo, objectNamespace) where
      contentMetaInfo is the ContentMetaInfo and objectNamespace.obj is the
      "other" info as a Blob or possibly deserialized into another type. If the
      hasSegments flag is True, when the segments are received and assembled
      into a single block of memory, this calls
      onGeneralizedObject(contentMetaInfo, objectNamespace) where
      contentMetaInfo is the ContentMetaInfo and objectNamespace.obj is the
      object that was assembled from the segment contents as a Blob or possibly
      deserialized to another type. If you don't supply an onGeneralizedObject
      callback here, you can call addOnStateChanged on the Namespace object to
      which this is attached and listen for the OBJECT_READY state.
    :type onGeneralizedObject: function object
    """
    def __init__(self, onGeneralizedObject = None):
        super(GeneralizedObjectHandler, self).__init__()

        # Instead of making this inherit from SegmentedObjectHandler, we create
        # one here and pass the method calls through.
        self._segmentedObjectHandler = SegmentedObjectHandler()
        # We'll call onGeneralizedObject if we don't use the SegmentedObjectHandler.
        self._onGeneralizedObject = onGeneralizedObject
        self._nComponentsAfterObjectNamespace = 0
        self._onObjectNeededId = 0

    def setNComponentsAfterObjectNamespace(self, nComponentsAfterObjectNamespace):
        """
        Set the number of name components after the object Namespace for
        fetching the generalized object, as described below.

        :param int nComponentsAfterObjectNamespace: If
          nComponentsAfterObjectNamespace is zero (the default), then require
          that the _meta and segment nodes are directly under the given
          Namespace name for the object. If nComponentsAfterObjectNamespace is
          greater than zero, allow exactly this number of name components after
          the given Namespace name but before the _meta and segment packets. In
          this case, the value of these name components may not be known before
          the first packet it fetched.
        :raises RuntimeError: If nComponentsAfterObjectNamespace is negative.
        """
        if nComponentsAfterObjectNamespace < 0:
            raise RuntimeError(
              "setNComponentsAfterObjectNamespace: The value cannot be negative")
        self._nComponentsAfterObjectNamespace = nComponentsAfterObjectNamespace

    def setObject(self, namespace, obj, contentType):
        """
        Create a _meta packet with the given contentType and as a child of the
        given Namespace. If the object is large enough to require segmenting,
        also segment the object and create child segment packets plus a
        signature _manifest packet of the given Namespace.

        :param Namespace namespace: The Namespace to append segment packets to.
          This ignores the Namespace from setNamespace().
        :param obj: The object to publish as a Generalized Object.
        :type obj: Blob or other type as determined by an attached handler
        :param str contentType: The content type for the content _meta packet.
        """
        hasSegments = (obj.size() >
          self._segmentedObjectHandler.getMaxSegmentPayloadLength())

        # Prepare the _meta packet.
        contentMetaInfo = ContentMetaInfo()
        contentMetaInfo.setContentType(contentType)
        contentMetaInfo.setTimestamp(Common.getNowMilliseconds())
        contentMetaInfo.setHasSegments(hasSegments)

        if not hasSegments:
            # We don't need to segment. Put the object in the "other" field.
            contentMetaInfo.setOther(obj);

        namespace[self.NAME_COMPONENT_META].serializeObject(
          contentMetaInfo.wireEncode())

        if hasSegments:
            self._segmentedObjectHandler.setObject(namespace, obj, True)
        else:
            # TODO: Do this in a canSerialize callback from Namespace.serializeObject?
            namespace._setObject(obj)

    def getInterestPipelineSize(self):
        """
        Get the number of outstanding interests which this maintains while
        fetching segments (if the ContentMetaInfo hasSegments is True).

        :return: The Interest pipeline size.
        :rtype: int
        """
        # Pass through to the SegmentedObjectHandler.
        return self._segmentedObjectHandler.getInterestPipelineSize()

    def setInterestPipelineSize(self, interestPipelineSize):
        """
        Set the number of outstanding interests which this maintains while
        fetching segments (if the ContentMetaInfo hasSegments is True).

        :param int interestPipelineSize: The Interest pipeline size.
        :raises RuntimeError: If interestPipelineSize is less than 1.
        """
        # Pass through to the SegmentedObjectHandler.
        self._segmentedObjectHandler.setInterestPipelineSize(interestPipelineSize)

    def getInitialInterestCount(self):
        """
        Get the initial Interest count (if the ContentMetaInfo hasSegments is
        True), as described in setInitialInterestCount.

        :return: The initial Interest count.
        :rtype: int
        """
        # Pass through to the SegmentedObjectHandler.
        return self._segmentedObjectHandler.getInitialInterestCount()

    def setInitialInterestCount(self, initialInterestCount):
        """
        Set the number of initial Interests to send for segments (if the
          ContentMetaInfo hasSegments is True). By default
          this just sends an Interest for the first segment and waits for the
          response before fetching more segments, but if you know the number of
          segments you can reduce latency by initially requesting more segments.
          (However, you should not use a number larger than the Interest
          pipeline size.)

        :param int initialInterestCount: The initial Interest count.
        :raises RuntimeError: If initialInterestCount is less than 1.
        """
        # Pass through to the SegmentedObjectHandler.
        self._segmentedObjectHandler.setInitialInterestCount(initialInterestCount)

    def getMaxSegmentPayloadLength(self):
        """
        Get the maximum length of the payload of one segment, used to split a
        larger payload into segments (if the ContentMetaInfo hasSegments is True).

        :return: The maximum payload length.
        :rtype: int
        """
        # Pass through to the SegmentedObjectHandler.
        return self._segmentedObjectHandler.getMaxSegmentPayloadLength()

    def setMaxSegmentPayloadLength(self, maxSegmentPayloadLength):
        """
        Set the maximum length of the payload of one segment, used to split a
        larger payload into segments (if the ContentMetaInfo hasSegments is True).

        :param int maxSegmentPayloadLength: The maximum payload length.
        """
        # Pass through to the SegmentedObjectHandler.
        self._segmentedObjectHandler.setMaxSegmentPayloadLength(maxSegmentPayloadLength)

    def _onNamespaceSet(self):
        self._onObjectNeededId = self.namespace.addOnObjectNeeded(self._onObjectNeeded)
        # We don't attach the SegmentedObjectHandler until we need it.

    def _onObjectNeeded(self, namespace, neededNamespace, id):
        if self._nComponentsAfterObjectNamespace > 0:
            # For extra components, we don't know the name of the _meta packet.
            return False

        if neededNamespace != self.namespace:
            # Don't respond for child namespaces (including when we call
            # objectNeeded on the _meta child below).
            return False

        # Remove the unused resource.
        self.namespace.removeCallback(self._onObjectNeededId)

        self.namespace[self.NAME_COMPONENT_META].objectNeeded()
        return True

    def _canDeserialize(self, blobNamespace, blob, onDeserialized):
        """
        This is called by Namespace when a packet is received. If this is the
        _meta packet, then decode it.
        """
        if (len(blobNamespace.name) !=
            len(self.namespace.name) + self._nComponentsAfterObjectNamespace + 1):
            # This is not a generalized object packet at the correct level
            # under the Namespace.
            return False;
        if blobNamespace.name[-1] != self.NAME_COMPONENT_META:
            # Not the _meta packet.
            if (self._nComponentsAfterObjectNamespace > 0 and
                (blobNamespace.getName()[-1].isSegment() or
                 blobNamespace.getName()[-1] == SegmentedObjectHandler.NAME_COMPONENT_MANIFEST)):
                # This is another packet type for a generalized object and we
                # did not try to fetch the _meta packet in onObjectNeeded. Try
                # fetching it if we haven't already.
                metaNamespace = blobNamespace.getParent()[self.NAME_COMPONENT_META]
                if metaNamespace.state < NamespaceState.INTEREST_EXPRESSED:
                    metaNamespace.objectNeeded()

            return False;

        # Decode the ContentMetaInfo.
        contentMetaInfo = ContentMetaInfo()
        # TODO: Report a deserializing error.
        contentMetaInfo.wireDecode(blob)

        # This will set the object for the _meta Namespace node.
        onDeserialized(contentMetaInfo)

        def onSegmentedObject(objectNamespace):
            if self._onGeneralizedObject:
                try:
                    self._onGeneralizedObject(contentMetaInfo, objectNamespace)
                except:
                    logging.exception("Error in onGeneralizedObject")

        objectNamespace = blobNamespace.parent
        if contentMetaInfo.getHasSegments():
            # Initiate fetching segments. This will call self._onGeneralizedObject.
            self._segmentedObjectHandler.addOnSegmentedObject(onSegmentedObject)
            self._segmentedObjectHandler.setNamespace(objectNamespace)
            # Explicitly request segment 0 to avoid fetching _meta, etc.
            objectNamespace[Name.Component.fromSegment(0)].objectNeeded()

            # Fetch the _manifest packet.
            # Debug: Verification should be handled by SegmentedObjectHandler.
            # TODO: How does SegmentedObjectHandler consumer know we're using a _manifest?
            objectNamespace[SegmentedObjectHandler.NAME_COMPONENT_MANIFEST].objectNeeded()
        else:
            # No segments, so the object is the ContentMetaInfo "other" Blob.
            # Deserialize and call the same callback as the segmentedObjectHandler.
            objectNamespace._deserialize(contentMetaInfo.getOther(), onSegmentedObject)

        return True

    NAME_COMPONENT_META = Name.Component("_meta")

    interestPipelineSize = property(getInterestPipelineSize, setInterestPipelineSize)
    initialInterestCount = property(getInitialInterestCount, setInitialInterestCount)
    maxSegmentPayloadLength = property(getMaxSegmentPayloadLength, setMaxSegmentPayloadLength)
