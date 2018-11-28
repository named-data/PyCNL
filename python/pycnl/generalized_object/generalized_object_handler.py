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

from pyndn import Name, MetaInfo
from pyndn.util import Blob
from pyndn.util.common import Common
from pycnl.namespace import Namespace
from pycnl.segmented_object_handler import SegmentedObjectHandler
from pycnl.generalized_object.content_meta_info import ContentMetaInfo

class GeneralizedObjectHandler(Namespace.Handler):
    """
    Create a GeneralizedObjectHandler with the optional onGeneralizedObject
    callback.

    :param onGeneralizedObject: (optional) When the ContentMetaInfo is received
      and the hasSegments is false, this calls
      onGeneralizedObject(contentMetaInfo, obj) where contentMetaInfo is the
      ContentMetaInfo and obj is the "other" info as a BlobObject or possibly
      deserialized into another type. If the hasSegments flag is true, when the
      segments are received and assembled into a single block of memory, this
      calls onGeneralizedObject(contentMetaInfo, obj) where contentMetaInfo is
      the ContentMetaInfo and obj is the object that was assembled from the
      segment contents as a BlobObject or possibly deserialized to another type.
      If you don't supply an onGeneralizedObject callback here, you can call
      addOnStateChanged on the Namespace object to which this is attached and
      listen for the OBJECT_READY state.
    :type onSegment: function object
    """
    def __init__(self, onGeneralizedObject = None):
        super(GeneralizedObjectHandler, self).__init__()

        # Instead of making this inherit from SegmentedObjectHandler, we create
        # one here and pass the method calls through.
        self._segmentedObjectHandler = SegmentedObjectHandler()
        # We'll call onGeneralizedObject if we don't use the SegmentedObjectHandler.
        self._onGeneralizedObject = onGeneralizedObject

    def getSegmentedObjectHandler(self):
        """
        Get the SegmentedObjectHandler which is used to segment an object and
        fetch segments. You can use this to set parameters such as
        getSegmentedObjectHandler().setInterestPipelineSize().

        :return: The SegmentedObjectHandler.
        :rtype: SegmentedObjectHandler
        """
        return self._segmentedObjectHandler

    def _onNamespaceSet(self):
        self.namespace.addOnObjectNeeded(self._onObjectNeeded)
        # We don't attach the SegmentedObjectHandler until we need it.

    def _onObjectNeeded(self, namespace, neededNamespace, id):
        if neededNamespace != self.namespace:
            # Don't respond for child namespaces (including when we call
            # objectNeeded on the _meta child below).
            return False

        self.namespace[self.NAME_COMPONENT_META].objectNeeded()
        return True

    def _canDeserialize(self, objectNamespace, blob, onDeserialized):
        """
        This is called by Namespace when a packet is received. If this is the
        _meta packet, then decode it.
        """
        if not (len(objectNamespace.name) == len(self.namespace.name) + 1 and
                objectNamespace.name[-1] == self.NAME_COMPONENT_META):
            # Not the _meta packet. Ignore.
            return False;

        # Decode the ContentMetaInfo.
        contentMetaInfo = ContentMetaInfo()
        # TODO: Report a deserializing error.
        contentMetaInfo.wireDecode(blob)

        # This will set the object for the _meta Namespace node.
        onDeserialized(contentMetaInfo)

        def onSegmentedObject(obj):
            if self._onGeneralizedObject:
                self._onGeneralizedObject(contentMetaInfo, obj)

        if contentMetaInfo.getHasSegments():
            # Initiate fetching segments. This will call self._onGeneralizedObject.
            self._segmentedObjectHandler.addOnSegmentedObject(onSegmentedObject)
            self._segmentedObjectHandler.setNamespace(self.namespace)
            self.namespace.objectNeeded()

            # TODO: Fetch the _manifest packet. How to override per-packet verification?
        else:
            # No segments, so the object is the ContentMetaInfo "other" Blob.
            # Deserialize and call the same callback as the segmentedObjectHandler.
            self.namespace._deserialize(contentMetaInfo.getOther(), onSegmentedObject)

        return True

    NAME_COMPONENT_META = Name.Component("_meta")
