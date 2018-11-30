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
This module defines the GeneralizedObjectStreamHandler class which extends
Namespace::Handler and attaches to a Namespace node to fetch the _latest packet
and use the name in it to start fetching the stream of generalized object using
a GeneralizedObjectHandler.
"""

import logging
from pyndn import Name, MetaInfo, DelegationSet
from pyndn.util.common import Common
from pycnl.namespace import Namespace, NamespaceState
from pycnl.generalized_object.generalized_object_handler import GeneralizedObjectHandler

class GeneralizedObjectStreamHandler(Namespace.Handler):
    """
    Create a GeneralizedObjectHandler with the optional
    onSequencedGeneralizedObject callback.

    :param int pipelineSize: (optional) The pipeline size (number of objects,
      not interests). The pipelineSize times the expected period between objects
      should be less than the maximum interest lifetime.
    :param onSequencedGeneralizedObject: (optional) When the ContentMetaInfo is
      received for a new sequence number and the hasSegments is false, this calls
      onSequencedGeneralizedObject(sequenceNumber, contentMetaInfo, object) where
      sequenceNumber is the new sequence number, contentMetaInfo is the
      ContentMetaInfo and object is the "other" info as a BlobObject or possibly
      deserialized into another type. If the hasSegments flag is true, when the
      segments are received and assembled into a single block of memory, this
      calls onSequencedGeneralizedObject(sequenceNumber, contentMetaInfo, object)
      where sequenceNumber is the new sequence number, contentMetaInfo is the
      ContentMetaInfo and object is the object that was assembled from the
      segment contents as a BlobObject or possibly deserialized to another type.
      If you don't supply an onGeneralizedObject callback here, you can call
      addOnStateChanged on the Namespace object to which this is attached and
      listen for the OBJECT_READY state.
    :type onSequencedGeneralizedObject: function object
    """
    def __init__(self, pipelineSize = 8, onSequencedGeneralizedObject = None):
        super(GeneralizedObjectStreamHandler, self).__init__()

        if pipelineSize < 1:
            pipelineSize = 1
        self._pipelineSize = pipelineSize
        self._onSequencedGeneralizedObject = onSequencedGeneralizedObject
        self._latestNamespace = None
        self._producedSequenceNumber = -1
        self._latestPacketFreshnessPeriod = 1000.0
        self._generalizedObjectHandler = GeneralizedObjectHandler()
        self._maxReportedSequenceNumber = -1

    def getGeneralizedObjectHandler(self):
        """
        Get the GeneralizedObjectHandler which is used to segment an object. You
        can use this to set parameters such as
        getGeneralizedObjectHandler().getSegmentedObjectHandler().setMaxSegmentPayloadLength().

        :return: The GeneralizedObjectHandler.
        :rtype: GeneralizedObjectHandler
        """
        return self._generalizedObjectHandler

    def setObject(self, sequenceNumber, obj, contentType):
        """
        Prepare the generalized object as a child of the given sequence number
        Namespace node under the getNamespace() node, according to
        GeneralizedObjectHandler.setObject. Also prepare to answer requests for
        the _latest packet which refer to the given sequence number Name.

        :param int sequenceNumber: The sequence number to publish. This updates
          the value for getProducedSequenceNumber()
        :param obj: The object to publish as a Generalized Object.
        :type obj: Blob or other type as determined by an attached handler
        :param str contentType: The content type for the content _meta packet.
        """
        if self.namespace == None:
            raise RuntimeError(
              "GeneralizedObjectStreamHandler.setObject: The Namespace is not set")

        self._producedSequenceNumber = sequenceNumber
        sequenceNamespace = self.namespace[
          Name.Component.fromSequenceNumber(self._producedSequenceNumber)]
        self._generalizedObjectHandler.setObject(
          sequenceNamespace, obj, contentType)

    def addObject(self, obj, contentType):
        """
        Publish an object for the next sequence number by calling setObject
        where the sequenceNumber is the current getProducedSequenceNumber() + 1.

        :param obj: The object to publish as a Generalized Object.
        :type obj: Blob or other type as determined by an attached handler
        :param str contentType: The content type for the content _meta packet.
        """
        self.setObject(self.getProducedSequenceNumber() + 1, obj, contentType)

    def getProducedSequenceNumber(self):
        """
        Get the latest produced sequence number.

        :return: The latest produced sequence number, or -1 if none have been
          produced.
        :rtype: int
        """
        return self._producedSequenceNumber

    def getLatestPacketFreshnessPeriod(self):
        """
        Get the freshness period to use for the produced _latest data packet.

        :return: The freshness period in milliseconds.
        :rtype: float
        """
        return self._latestPacketFreshnessPeriod

    def setLatestPacketFreshnessPeriod(self, latestPacketFreshnessPeriod):
        """
        Set the freshness period to use for the produced _latest data packet.

        :param float latestPacketFreshnessPeriod: The freshness period in
          milliseconds.
        """
        self._latestPacketFreshnessPeriod = Common.nonNegativeFloatOrNone(
          latestPacketFreshnessPeriod)

    def _onNamespaceSet(self):
        self._latestNamespace = self.namespace[self.NAME_COMPONENT_LATEST]

        self.namespace.addOnObjectNeeded(self._onObjectNeeded)
        self.namespace.addOnStateChanged(self._onStateChanged)

    def _onObjectNeeded(self, namespace, neededNamespace, callbackId):
        """
        This is called for object needed at the Handler's namespace. If
        neededNamespace is the Handler's Namespace (called by the appliction),
        then fetch the _latest packet. If neededNamespace is for the _latest
        packet (from an incoming Interest), produce the _latest packet for the
        current sequence number.
        """
        if neededNamespace == self.namespace:
            # Assume this is called by a consumer. Fetch the _latest packet.
            self._latestNamespace.objectNeeded(True)
            return True

        if (neededNamespace == self._latestNamespace and
              self._producedSequenceNumber >= 0):
            # Produce the _latest Data packet.
            sequenceName = Name(self.namespace.name).append(
              Name.Component.fromSequenceNumber(self._producedSequenceNumber))
            delegations = DelegationSet()
            delegations.add(1, sequenceName)

            versionedLatest = self._latestNamespace[Name.Component.fromVersion
              (Common.getNowMilliseconds())]
            metaInfo = MetaInfo()
            metaInfo.setFreshnessPeriod(self._latestPacketFreshnessPeriod)
            versionedLatest.setNewDataMetaInfo(metaInfo)
            # Make the Data packet and reply to outstanding Interests.
            versionedLatest.serializeObject(delegations.wireEncode())

            return True

        return False

    def _onStateChanged(self, namespace, changedNamespace, state, callbackId):
        """
        This is called when a packet arrives. Parse the _latest packet and start
        fetching the stream of GeneralizedObject by sequence number.
        """
        if (not (state == NamespaceState.OBJECT_READY and
                 changedNamespace.name.size() ==
                   self._latestNamespace.name.size() + 1 and
                 self._latestNamespace.name.isPrefixOf(changedNamespace.name) and
                 changedNamespace.name[-1].isVersion())):
            # Not a versioned _latest, so ignore.
            return

        # Decode the _latest packet to get the target to fetch.
        # TODO: Should this already have been done by deserialize()?)
        delegations = DelegationSet()
        delegations.wireDecode(changedNamespace.obj)
        if delegations.size() <= 0:
            return
        targetName = delegations.get(0).getName()
        if (not (self.namespace.name.isPrefixOf(targetName) and
                 targetName.size() == self.namespace.name.size() + 1 and
                 targetName[-1].isSequenceNumber())):
            # TODO: Report an error for invalid target name?
            return
        targetNamespace = self.namespace[targetName]

        # We may already have the target if this was triggered by the producer.
        if targetNamespace.obj == None:
            sequenceNumber = targetName[-1].toSequenceNumber()
            self._maxReportedSequenceNumber = sequenceNumber - 1
            self._requestNewSequenceNumbers()

    def _requestNewSequenceNumbers(self):
        """
        Request new child sequence numbers, up to the pipelineSize_.
        """
        childComponents = self.namespace.getChildComponents()
        # First, count how many are already requested and not received.
        nRequestedSequenceNumbers = 0
        # Debug: Track the max requested (and don't search all children).
        for component in childComponents:
            if not component.isSequenceNumber():
                # The namespace contains a child other than a sequence number. Ignore.
                continue

            # TODO: Should the child sequence be set to INTEREST_EXPRESSED along with _meta?
            metaChild = self.namespace[component][
              GeneralizedObjectHandler.NAME_COMPONENT_META]
            if (metaChild.data == None and
                metaChild.state >= NamespaceState.INTEREST_EXPRESSED):
                nRequestedSequenceNumbers += 1
                if nRequestedSequenceNumbers >= self._pipelineSize:
                    # Already maxed out on requests.
                    break

        # Now find unrequested sequence numbers and request.
        sequenceNumber = self._maxReportedSequenceNumber
        while nRequestedSequenceNumbers < self._pipelineSize:
            sequenceNumber += 1
            sequenceNamespace = self.namespace[
              Name.Component.fromSequenceNumber(sequenceNumber)]
            sequenceMeta = sequenceNamespace[
              GeneralizedObjectHandler.NAME_COMPONENT_META]
            if (sequenceMeta.data or
                sequenceMeta.state >= NamespaceState.INTEREST_EXPRESSED):
                # Already got the data packet or already requested.
                continue

            nRequestedSequenceNumbers += 1
            # We are in loop scope, su use a factory function to capture sequenceNumber.
            def makeOnGeneralizedObject(sequenceNumber):
                def onGeneralizedObject(contentMetaInfo, obj):
                    try:
                        self._onSequencedGeneralizedObject(
                          sequenceNumber, contentMetaInfo, obj)
                    except:
                        logging.exception("Error in onSequencedGeneralizedObject")

                    if sequenceNumber > self._maxReportedSequenceNumber:
                        self._maxReportedSequenceNumber = sequenceNumber
                    self._requestNewSequenceNumbers()
                return onGeneralizedObject

            # Debug: Do we have to attach a new handler for each sequence number?
            generalizedObjectHandler = GeneralizedObjectHandler(
              makeOnGeneralizedObject(sequenceNumber))
            sequenceNamespace.setHandler(generalizedObjectHandler)
            sequenceMeta.objectNeeded()

    NAME_COMPONENT_LATEST = Name.Component("_latest")
