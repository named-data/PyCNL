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

from pyndn import Name
from pycnl.namespace import Namespace
from pycnl.segmented_object_handler import SegmentedObjectHandler
from pycnl.generalized_object.content_meta_info import ContentMetaInfo

class GeneralizedObjectHandler(Namespace.Handler):
    """
    Create a GeneralizedObjectHandler with the optional onGeneralizedObject
    callback.

    :param onGeneralizedObject: (optional) When the ContentMetaInfo is received
      and the hasSegments is false, this calls
      onGeneralizedObject(contentMetaInfo, other) where contentMetaInfo is the
      ContentMetaInfo and other is the "other" info. If the hasSegments flag is
      true, when the segments are received and assembled into a single block of
      memory, this calls onGeneralizedObject(contentBlob) where contentBlob is
      the Blob, assembled from the segment contents. If you don't supply an
      onGeneralizedObject callback here, you can call addOnStateChanged on the
      Namespace object to which this is attached and listen for the OBJECT_READY
      state.
    :type onSegment: function object
    """
    def __init__(self, onGeneralizedObject = None):
        super(GeneralizedObjectHandler, self).__init__()

        # Instead of making this inherit from SegmentedObjectHandler, we create
        # one here and pass the method calls through.
        self._segmentedObjectHandler = SegmentedObjectHandler()
        # We'll call onGeneralizedObject if we don't use the SegmentedObjectHandler.
        self._onGeneralizedObject = onGeneralizedObject

    def addOnSegment(self, onSegment):
        """
        Add an onSegment callback. When a new segment is available, this calls
        onSegment as described below. Segments are supplied in order.
        This is only used if the ContentMetaInfo hasSegments flag is true.

        :param onSegment: This calls onSegment(segmentNamespace) where
          segmentNamespace is the Namespace where you can use
          segmentNamespace.getObject(). You must check if segmentNamespace is
          None because after supplying the final segment, this calls
          onSegment(None) to signal the "end of stream".
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        :type onSegment: function object
        :return: The callback ID which you can use in removeCallback().
        :rtype: int
        """
        # Pass through to the _segmentedObjectHandler.
        return self._segmentedObjectHandler.addOnSegment(onSegment)

    def removeCallback(self, callbackId):
        """
        Remove the callback with the given callbackId. If the callbackId isn't
        found, do nothing.

        :param int callbackId: The callback ID returned, for example, from
          addOnSegment.
        """
        # Pass through to the _segmentedObjectHandler.
        self._segmentedObjectHandler.removeCallback(callbackId)

    def getInterestPipelineSize(self):
        """
        Get the number of outstanding interests which this maintains while
        fetching segments.
        This is only used if the ContentMetaInfo hasSegments flag is true.

        :return: The Interest pipeline size.
        :rtype: int
        """
        # Pass through to the _segmentedObjectHandler.
        return self._segmentedObjectHandler.getInterestPipelineSize()

    def setInterestPipelineSize(self, interestPipelineSize):
        """
        Set the number of outstanding interests which this maintains while
        fetching segments.
        This is only used if the ContentMetaInfo hasSegments flag is true.

        :param int interestPipelineSize: The Interest pipeline size.
        :raises RuntimeError: If interestPipelineSize is less than 1.
        """
        # Pass through to the _segmentedObjectHandler.
        self._segmentedObjectHandler.setInterestPipelineSize(interestPipelineSize)

    def getInitialInterestCount(self):
        """
        Get the initial Interest count (as described in setInitialInterestCount).
        This is only used if the ContentMetaInfo hasSegments flag is true.

        :return: The initial Interest count.
        :rtype: int
        """
        # Pass through to the _segmentedObjectHandler.
        return self._segmentedObjectHandler.getInitialInterestCount()

    def setInitialInterestCount(self, initialInterestCount):
        """
        Set the number of initial Interests to send for segments. By default
          this just sends an Interest for the first segment and waits for the
          response before fetching more segments, but if you know the number of
          segments you can reduce latency by initially requesting more segments.
          (However, you should not use a number larger than the Interest
          pipeline size.)
        This is only used if the ContentMetaInfo hasSegments flag is true.

        :param int initialInterestCount: The initial Interest count.
        :raises RuntimeError: If initialInterestCount is less than 1.
        """
        # Pass through to the _segmentedObjectHandler.
        self._segmentedObjectHandler.setInitialInterestCount(initialInterestCount)

    def _onNamespaceSet(self):
        self.namespace.addOnObjectNeeded(self._onObjectNeeded)
        # We don't attach the SegmentedObjectHandler until we need it.

    def _onObjectNeeded(self, namespace, neededNamespace, id):
        if neededNamespace != self.getNamespace():
            # Don't respond for child namespaces (including when we call
            # objectNeeded on the _meta child below).
            return False

        self.getNamespace()[GeneralizedObjectHandler.NAME_COMPONENT_META].objectNeeded()
        return True

    def _canDeserialize(self, objectNamespace, blob, onDeserialized):
        """
        This is called by Namespace when a packet is received. If this is the
        _meta packet, then decode it.
        """
        if not (len(objectNamespace.name) == len(self.getNamespace().name) + 1 and
                objectNamespace.name[-1] ==
                  GeneralizedObjectHandler.NAME_COMPONENT_META):
            # Not the _meta packet. Ignore.
            return False;

        # Decode the ContentMetaInfo.
        contentMetaInfo = ContentMetaInfo()
        # TODO: Report a deserializing error.
        contentMetaInfo.wireDecode(blob)

        # This will set the object for the _meta Namespace node.
        onDeserialized(contentMetaInfo)

        if contentMetaInfo.getHasSegments():
            # Initiate fetching segments. This will call self._onGeneralizedObject.
            def onSegmentedObject(obj):
                if self._onGeneralizedObject:
                    self._onGeneralizedObject(contentMetaInfo, obj)

            self._segmentedObjectHandler.addOnSegmentedObject(onSegmentedObject)
            self._segmentedObjectHandler.setNamespace(self.getNamespace())
            self.getNamespace().objectNeeded()

            # TODO: Fetch the _manifest packet. How to override per-packet verification?
        else:
            # No segments, so the object is the ContentMetaInfo "other" Blob.
            self.getNamespace().setObject(contentMetaInfo.getOther())

            if self._onGeneralizedObject:
                self._onGeneralizedObject(
                  contentMetaInfo, contentMetaInfo.getOther())

        return True

    NAME_COMPONENT_META = Name.Component("_meta")
    NAME_COMPONENT_MANIFEST = Name.Component("_manifest")

    interestPipelineSize = property(getInterestPipelineSize, setInterestPipelineSize)
    initialInterestCount = property(getInitialInterestCount, setInitialInterestCount)
