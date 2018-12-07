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
This module defines the Namespace class which is the main class that represents
the name tree and related operations to manage it.
"""

import bisect
import threading
import logging
from pyndn import Name, Interest, Data, MetaInfo
from pyndn.util import Blob, ExponentialReExpress
from pyndn.util.common import Common
from pyndn.encrypt import EncryptedContent
from pycnl.impl.pending_incoming_interest_table import PendingIncomingInterestTable

class Namespace(object):
    """
    Create a Namespace object with the given name, and with no parent. This
    is the root of the name tree. To create child nodes, use
    myNamespace.getChild("foo") or myNamespace["foo"].

    :param Name name: The name of this root node in the namespace. This
      makes a copy of the name.
    :param KeyChain keyChain: (optional) The KeyChain for signing packets,
      if needed. You can also call setKeyChain().
    """
    def __init__(self, name, keyChain = None):
        self._name = Name(name)
        # _parent and _root may be updated by _createChild.
        self._parent = None
        self._root = self
        # The dictionary key is a Name.Component. The value is the child Namespace.
        self._children = {}
        # The keys of _children in sorted order, kept in sync with _children.
        # (We don't use OrderedDict because it doesn't sort keys on insert.)
        self._sortedChildrenKeys = []
        self._state = NamespaceState.NAME_EXISTS
        self._networkNack = None
        self._validateState = NamespaceValidateState.WAITING_FOR_DATA
        self._validationError = None
        self._freshnessExpiryTimeMilliseconds = None
        self._data = None
        self._object = None
        self._face = None
        self._keyChain = keyChain
        self._newDataMetaInfo = None
        self._decryptor = None
        self._decryptionError = ""
        self._signingError = ""
        self._handler = None
        # The dictionary key is the callback ID. The value is the onStateChanged function.
        self._onStateChangedCallbacks = {}
        # The dictionary key is the callback ID. The value is the onValidateStateChanged function.
        self._onValidateStateChangedCallbacks = {}
        self._onObjectNeededCallbacks = {}
        # setFace will create this in the root Namespace node.
        self._pendingIncomingInterestTable = None
        self._maxInterestLifetime = None

    class Handler(object):
        def __init__(self):
            self._namespace = None

        def setNamespace(self, namespace):
            """
            Set the Namespace that this handler is attached to. (This is
            automatically called when you call Namespace.setHandler.) This
            method does not attach this Handler to the Namespace.

            :param Namespace namespace: The Handler's Namespace.
            :return: This Handler so you can chain calls to update values.
            :rtype: Namespace.Handler
            :raises RuntimeError: If this Handler is already attached to a
              different Namespace.
            """
            if self._namespace != None and self._namespace != namespace:
                raise RuntimeError(
                  "This Handler is already attached to a different Namespace object")

            self._namespace = namespace
            self._onNamespaceSet()

            return self

        def getNamespace(self):
            """
            Get the Namespace that this Handler is attached to.

            :return: This Handler's Namespace, or None if this Handler is not
              attached to a Namespace.
            :rtype: Namespace
            """
            return self._namespace

        def _canDeserialize(self, objectNamespace, blob, onDeserialized):
            """
            An internal method to check if this Handler can deserialize the blob
            in order to set the object for the objectNamespace. This should only
            be called by the Namespace class. This base implementation just
            returns False. The subclass can override.

            :param Namespace objectNamespace: The Namespace node which needs its
              object deserialized.
            :param Blob blob: The serialized bytes to deserialize.
            :param onDeserialized: If the Handler can deserialize, it should
              return True and eventually call onDeserialized(obj) with the
              deserialized object.
            :type onDeserialized: function object
            :return: True if this Handler can deserialize and will call
              onDeserialized, otherwise False.
            """
            return False

        def _onNamespaceSet(self):
            """
            This protected method is called after this Handler's Namespace field
            is set by attaching it. A subclass can override to perform actions
            with getNamespace() such as adding callbacks to the Namespace.
            """
            pass

        namespace = property(getNamespace)

    def getName(self):
        """
        Get the name of this node in the name tree. This includes the name
        components of parent nodes. To get the name component of just this node,
        use getName()[-1].

        :return: The name of this namespace. NOTE: You must not change the
          name - if you need to change it then make a copy.
        :rtype: Name
        """
        return self._name

    def getParent(self):
        """
        Get the parent namespace.

        :return: The parent namespace, or None if this is the root of the tree.
        :rtype: Namespace
        """
        return self._parent

    def getRoot(self):
        """
        Get the root namespace (which has no parent node).

        :return: The root namespace.
        :rtype: Namespace
        """
        return self._root

    def getState(self):
        """
        Get the state of this Namespace node. When a Namespace node is first
        created, its state is NamespaceState.NAME_EXISTS .

        :return: The state of this Namespace node.
        :rtype: An int from the NamespaceState enum.
        """
        return self._state

    def getNetworkNack(self):
        """
        Get the NetworkNack for when the state is set to
        NamespaceState.INTEREST_NETWORK_NACK .

        :return: The NetworkNack, or None if one wasn't received.
        :rtype: NetworkNack
        """
        return self._networkNack

    def getValidateState(self):
        """
        Get the validate state of this Namespace node. When a Namespace node is
        first created, its validate state is
        NamespaceValidateState.WAITING_FOR_DATA .

        :return: The validate state of this Namespace node.
        :rtype: An int from the NamespaceValidateState enum.
        """
        return self._validateState

    def getValidationError(self):
        """
        Get the ValidationError for when the state is set to
        NamespaceValidateState.VALIDATE_FAILURE .

        :return: The ValidationError, or None if it hasn't been set due to a
          VALIDATE_FAILURE.
        :rtype: ValidationError
        """
        return self._validationError

    def getDecryptionError(self):
        """
        Get the decryption error for when the state is set to
        NamespaceState.DECRYPTION_ERROR .

        :return: The decryption error, or "" if it hasn't been set due to a
          DECRYPTION_ERROR.
        :rtype: str
        """
        return self._decryptionError

    def getSigningError(self):
        """
        Get the signing error for when the state is set to
        NamespaceState.SIGNING_ERROR .

        :return: The signing error, or "" if it hasn't been set due to a
          SIGNING_ERROR.
        :rtype: str
        """
        return self._signingError

    def hasChild(self, nameOrComponent):
        """
        Check if this node in the namespace has the given child (or decendant).

        :param nameOrComponent: If this is a Name, check if there is a
          descendant node with the name (which must have this node's name as a
          prefix). Otherwise, this is the name component of the child to check.
        :type component: Name or Name.Component or value for the Name.Component
          constructor
        :return: True if this has a child with the name or name component. This
          also returns True if nameOrComponent is a Name that equals the name of
          this node.
        :rtype: bool
        """
        if isinstance(nameOrComponent, Name):
            descendantName = nameOrComponent
            if not self._name.isPrefixOf(descendantName):
                raise RuntimeError(
                  "The name of this node is not a prefix of the descendant name")

            if descendantName.size() == self._name.size():
                # A trivial case where it is already the name of this node.
                return True

            # Find the child node whose name equals the descendantName.
            # We know descendantNamespace is a prefix, so we can just go by
            # component count instead of a full compare.
            descendantNamespace = self
            while True:
                nextComponent = descendantName[descendantNamespace._name.size()]
                if not (nextComponent in descendantNamespace._children):
                    return False

                if descendantNamespace._name.size() + 1 == descendantName.size():
                    # nextComponent is the final component.
                    return True
                descendantNamespace = descendantNamespace._children[nextComponent]
        else:
            component = nameOrComponent
            if not isinstance(component, Name.Component):
                component = Name.Component(component)

            return component in self._children

    def getChild(self, nameOrComponent):
        """
        Get a child (or descendant), creating it if needed. This is equivalent
        to namespace[component]. If a child is created, this calls callbacks as
        described by addOnStateChanged (but does not call the callbacks when
        creating intermediate nodes).

        :param nameOrComponent: If this is a Name, find or create the descendant
          node with the name (which must have this node's name as a prefix).
          Otherwise, this is the name component of the immediate child.
        :type nameOrComponent: Name or Name.Component or value for the
          Name.Component constructor
        :return: The child Namespace object. If nameOrComponent is a Name which
          equals the name of this Namespace, then just return this Namespace.
        :rtype: Namespace
        :raises RuntimeError: If the name of this Namespace node is not a prefix
          of the given Name.
        """
        if isinstance(nameOrComponent, Name):
            descendantName = nameOrComponent
            if not self._name.isPrefixOf(descendantName):
                raise RuntimeError(
                  "The name of this node is not a prefix of the descendant name")

            # Find or create the child node whose name equals the descendantName.
            # We know descendantNamespace is a prefix, so we can just go by
            # component count instead of a full compare.
            descendantNamespace = self
            while descendantNamespace._name.size() < descendantName.size():
                nextComponent = descendantName[descendantNamespace._name.size()]
                if nextComponent in descendantNamespace._children:
                    descendantNamespace = descendantNamespace._children[nextComponent]
                else:
                    # Only fire the callbacks for the leaf node.
                    isLeaf = (
                      descendantNamespace._name.size() == descendantName.size() - 1)
                    descendantNamespace = descendantNamespace._createChild(
                      nextComponent, isLeaf)

            return descendantNamespace
        else:
            component = nameOrComponent
            if not isinstance(component, Name.Component):
                component = Name.Component(component)

            if component in self._children:
                return self._children[component]
            else:
                return self._createChild(component, True)

    def getChildComponents(self):
        """
        Get a list of the name component of all child nodes.

        :return: A fresh sorted list of the name component of all child nodes.
          This remains the same if child nodes are added or deleted.
        :rtype: list of Name.Component
        """
        return self._sortedChildrenKeys[:]

    def serializeObject(self, obj):
        # TODO: What if this node already has a _data and/or _object?

        # TODO: Call handler canSerialize and set state SERIALIZING.
        # (Does this happen in a different place from onObjectNeeded?)
        # (If the handler can't serialize and this node has children, should abort?)

        if not isinstance(obj, Blob):
            raise RuntimeError(
              "serializeObject: For the default serialize, the object must be a Blob")

        keyChain = self._getKeyChain()
        if keyChain == None:
            raise RuntimeError(
              "serializeObject: There is no KeyChain, so can't serialize " +
              self._name.toUri())

        # TODO: Encrypt and set state ENCRYPTING.

        # Prepare the Data packet.
        data = Data(self._name)
        data.setContent(obj)
        metaInfo = self._getNewDataMetaInfo()
        if metaInfo != None:
            data.setMetaInfo(metaInfo)

        self._setState(NamespaceState.SIGNING)
        try:
            keyChain.sign(data)
        except Exception as ex:
            self._signingError = (
              "Error signing the serialized Data: " + repr(ex))
            self._setState(NamespaceState.SIGNING_ERROR)
            return

        # This calls satisfyInterests.
        self.setData(data)

        self._setObject(obj)

    def _setObject(self, obj):
        self._object = obj
        self._setState(NamespaceState.OBJECT_READY)

    def setData(self, data):
        """
        Attach the Data packet to this Namespace and satisfy pending Interests
        for it. However, if a Data packet is already attached, do nothing. This
        does not update the Namespace state, decrypt, verify or deserialize.

        :param Data data: The Data packet object whose name must equal the name
          in this Namespace node. To get the right Namespace, you can use
          getChild(data.getName()). For efficiency, this does not copy the Data
          packet object. If your application may change the object later, then
          you must call setData with a copy of the object.
        :return: True if the Data packet is attached, False if a Data packet was
          already attached.
        :rtype: bool
        :raises RuntimeError: If the Data packet name does not equal the name of
          this Namespace node.
        """
        if self._data != None:
            # We already have an attached object.
            return False
        if not data.name.equals(self._name):
            raise RuntimeError(
              "The Data packet name does not equal the name of this Namespace node.")

        if self._root._pendingIncomingInterestTable != None:
            # Quickly send the Data packet to satisfy interests, before calling callbacks.
            self._root._pendingIncomingInterestTable.satisfyInterests(data)

        if (data.getMetaInfo().getFreshnessPeriod() != None and
            data.getMetaInfo().getFreshnessPeriod() >= 0.0):
            self._freshnessExpiryTimeMilliseconds = (Common.getNowMilliseconds() +
              data.getMetaInfo().getFreshnessPeriod())
        else:
            # Does not expire.
            self._freshnessExpiryTimeMilliseconds = None
        self._data = data

        return True

    def getData(self):
        """
        Get the Data packet attached to this Namespace object. Note that
        getObject() may be different than the content in the attached Data
        packet (for example if the content is decrypted). To get the deserialized
        content, you should use getObject() instead of getData().getContent().
        Also, the Data packet name is the same as the name of this Namespace node,
        so you can simply use getName() instead of getData().getName(). You
        should only use getData() to get other information such as the MetaInfo.
        (It is possible that this Namespace object has an attacked Data packet,
        but getObject() is still None because this state has not yet changed
        to NamespaceState.OBJECT_READY.)

        :return: The Data packet object, or None if not set.
        :rtype: Data
        """
        return self._data

    def getAllData(self, dataList):
        """
        Recursively append to the Data packets for this and children nodes to
        the given list.

        :param Array<Data> dataList: Append the Data packets to this list. This
          does not first clear the list. You should not modify the returned Data
          packets. If you need to modify one, then make a copy.
        """
        if self._data != None:
            dataList.append(self._data)

        if len(self._children) > 0:
            for child in self._sortedChildrenKeys:
                self._children[child].getAllData(dataList)

    def getObject(self):
        """
        Get the deserialized object attached to this Namespace object. Note that
        getObject() may be different than the content in the attached Data
        packet (for example if the content is decrypted). In the default
        behavior, the object is the Blob content of the Data packet, but may be
        a different type as determined by the attached handler.

        :return: The object which is a Blob or other type as determined by the
           attached handler. You must cast to the correct type. If the object
           is not set, return None.
        :rtype: Blob or other type as determined by the attached handler
        """
        return self._object

    def addOnStateChanged(self, onStateChanged):
        """
        Add an onStateChanged callback. When the state changes in this namespace
        at this node or any children, this calls onStateChanged as described
        below.

        :param onStateChanged: This calls
          onStateChanged(namespace, changedNamespace, state, callbackId)
          where namespace is this Namespace, changedNamespace is the Namespace
          (possibly a child) whose state has changed, state is the new state as
          an int from the NamespaceState enum, and callbackId is the callback ID
          returned by this method. If you only care if the state has changed for
          this Namespace (and not any of its children) then your callback can
          check "if changedNamespace == namespace". (Note that the state given
          to the callback may be different than changedNamespace.getState() if
          other processing has changed the state before this callback is called.)
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        :type onStateChanged: function object
        :return: The callback ID which you can use in removeCallback().
        :rtype: int
        """
        callbackId = Namespace.getNextCallbackId()
        self._onStateChangedCallbacks[callbackId] = onStateChanged
        return callbackId

    def addOnValidateStateChanged(self, onValidateStateChanged):
        """
        Add an onValidateStateChanged callback. When the validate state changes
        in this namespace at this node or any children, this calls
        onValidateStateChanged as described below.

        :param onValidateStateChanged: This calls
          onValidateStateChanged(namespace, changedNamespace, validateState, callbackId)
          where namespace is this Namespace, changedNamespace is the Namespace
          (possibly a child) whose validate state has changed, validateState is
          the new validate state as an int from the NamespaceValidateState enum,
          and callbackId is the callback ID returned by this method. If you only
          care if the validate state has changed for this Namespace (and not any
          of its children) then your callback can check
          "if changedNamespace == namespace". (Note that the validate state
          given to the callback may be different than
          changedNamespace.getValidateState() if other processing has changed
          the validate state before this callback is called.)
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        :type onValidateStateChanged: function object
        :return: The callback ID which you can use in removeCallback().
        :rtype: int
        """
        callbackId = Namespace.getNextCallbackId()
        self._onValidateStateChangedCallbacks[callbackId] = onValidateStateChanged
        return callbackId

    def addOnObjectNeeded(self, onObjectNeeded):
        """
        Add an onObjectNeeded callback. The objectNeeded() method calls all the
        onObjectNeeded callback on that Namespace node and all the parents, as
        described below.

        :param onObjectNeeded: This calls
          onObjectNeeded(namespace, neededNamespace, callbackId)
          where namespace is this Namespace, neededNamespace is the Namespace
          (possibly a child) whose objectNeeded was called, and callbackId
          is the callback ID returned by this method. If the owner of the
          callback (the application or a Handler) can produce the object for
          the neededNamespace, then the callback should return True and the
          owner should produce the object (either during the callback or at a
          later time) and call neededNamespace.serializeObject(). If the owner
          cannot produce the object then the callback should return False.
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        :type onObjectNeeded: function object
        :return: The callback ID which you can use in removeCallback().
        :rtype: int
        """
        callbackId = Namespace.getNextCallbackId()
        self._onObjectNeededCallbacks[callbackId] = onObjectNeeded
        return callbackId

    def removeCallback(self, callbackId):
        """
        Remove the callback with the given callbackId. This does not search for
        the callbackId in child nodes. If the callbackId isn't found, do nothing.

        :param int callbackId: The callback ID returned, for example, from
          addOnStateChanged.
        """
        self._onStateChangedCallbacks.pop(callbackId, None)
        self._onValidateStateChangedCallbacks.pop(callbackId, None)

    def setFace(self, face, onRegisterFailed = None, onRegisterSuccess = None):
        """
        Set the Face used when expressInterest is called on this or child nodes
        (unless a child node has a different Face), and optionally register to
        receive Interest packets under this prefix and answer with Data packets.
        TODO: Replace this by a mechanism for requesting a Data object which is
        more general than a Face network operation.

        :param Face face: The Face object. If this Namespace object already has
          a Face object, it is replaced.
        :param onRegisterFailed: (optional) Call face.registerPrefix to
          register to receive Interest packets under this prefix, and if
          register prefix fails for any reason, this calls
          onRegisterFailed(prefix). However, if onRegisterFailed is omitted, do
          not register to receive Interests.
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        :type onRegisterFailed: function object
        :param onRegisterSuccess: (optional) This calls
          onRegisterSuccess(prefix, registeredPrefixId) when this receives a
          success message from the forwarder. If onRegisterSuccess is None or
          omitted, this does not use it. (The onRegisterSuccess parameter comes
          after onRegisterFailed because it can be None or omitted, unlike
          onRegisterFailed.)
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        """
        self._face = face

        if onRegisterFailed != None:
            if self._root._pendingIncomingInterestTable == None:
                # All _onInterest callbacks share this in the root node.
                # When we add a new data packet to a Namespace node, we will
                # also check if it satisfies a pending interest.
                self._root._pendingIncomingInterestTable = PendingIncomingInterestTable()

            face.registerPrefix(
              self._name, self._onInterest, onRegisterFailed, onRegisterSuccess)

    def setKeyChain(self, keyChain):
        """
        Set the KeyChain used to sign packets (if needed) at this or child
        nodes. If a KeyChain already exists at this node, it is replaced.

        :param KeyChain keyChain: The KeyChain.
        """
        self._keyChain = keyChain

    def _getKeyChain(self):
        """
        Get the KeyChain set by setKeyChain (or the NameSpace constructor) on
        this or a parent Namespace node. This method name has an underscore
        because is normally only called from a Handler, not from the application.

        :return: The KeyChain, or None if not set on this or any parent.
        :rtype: KeyChain
        """
        namespace = self
        while namespace != None:
            if namespace._keyChain != None:
                return namespace._keyChain
            namespace = namespace._parent

        return None

    def setNewDataMetaInfo(self, metaInfo):
        """
        Set the MetaInfo to use when creating a new Data packet at this or child
        nodes. If a MetaInfo already exists at this node, it is replaced.

        :param MetaInfo metaInfo: The MetaInfo object, which is copied.
        """
        self._newDataMetaInfo = MetaInfo(metaInfo)

    def setDecryptor(self, decryptor):
        """
        Set the decryptor used to decrypt the EncryptedContent of a Data packet
        at this or child nodes. If a decryptor already exists at this node, it
        is replaced.

        :param DecryptorV2 decryptor: The decryptor.
        """
        self._decryptor = decryptor

    def setHandler(self, handler):
        if handler == None:
            # Clear the Handler.
            self._handler = None
            return

        if self._handler != None:
            # TODO: Should we try to chain handlers?
            raise ValueError("This Namespace node already has a handler")

        handler.setNamespace(self)
        self._handler = handler
        return self

    def objectNeeded(self, mustBeFresh = False):
        # Check if we already have the object.
        interest = Interest(self._name)
        # TODO: Make the lifetime configurable.
        interest.setInterestLifetimeMilliseconds(4000.0)
        interest.setMustBeFresh(mustBeFresh)
        # Debug: This requires a Data packet. Check for an object without one?
        bestMatch = self._findBestMatchName(
          self, interest, Common.getNowMilliseconds())
        if bestMatch != None and bestMatch._object != None:
            # Set the state again to fire the callbacks.
            bestMatch._setState(NamespaceState.OBJECT_READY)
            return

        # Ask all OnObjectNeeded callbacks if they can produce.
        canProduce = False
        namespace = self
        while namespace != None:
            if namespace._fireOnObjectNeeded(self):
                canProduce = True
            namespace = namespace._parent

        # Debug: Check if the object has been set (even if onObjectNeeded returned False.)

        if canProduce:
            # Assume that the application will produce the object.
            self._setState(NamespaceState.PRODUCING_OBJECT)
            return

        # Express the interest.
        face = self._getFace()
        if face == None:
            raise RuntimeError("A Face object has not been set for this or a parent.")
        # TODO: What if the state is already INTEREST_EXPRESSED?
        self._setState(NamespaceState.INTEREST_EXPRESSED)
        def onTimeout(interest):
            # TODO: Need to detect a timeout on a child node.
            self._setState(NamespaceState.INTEREST_TIMEOUT)
        def onNetworkNack(interest, networkNack):
            # TODO: Need to detect a network nack on a child node.
            self._networkNack = networkNack
            self._setState(NamespaceState.INTEREST_NETWORK_NACK)
        face.expressInterest(
          interest, self._onData,
          ExponentialReExpress.makeOnTimeout(
            face, self._onData, onTimeout, self._getMaxInterestLifetime()),
          onNetworkNack)

    def setMaxInterestLifetime(self, maxInterestLifetime):
        """
        Set the maximum lifetime for re-expressed interests to be used when this
        or a child node calls expressInterest. You can call this on a child node
        to set a different maximum lifetime. If you don't set this, the default
        is 16000 milliseconds.

        :param float maxInterestLifetime: The maximum lifetime in
          milliseconds.
        """
        self._maxInterestLifetime = maxInterestLifetime

    def _getFace(self):
        """
        Get the Face set by setFace on this or a parent Namespace node. This
        method name has an underscore because is normally only called from a
        Handler, not from the application.

        :return: The Face, or None if not set on this or any parent.
        :rtype: Face
        """
        namespace = self
        while namespace != None:
            if namespace._face != None:
                return namespace._face
            namespace = namespace._parent

        return None

    def _getDecryptor(self):
        """
        Get the decryptor set by setDecryptor on this or a parent Namespace node.

        :return: The decryptor, or None if not set on this or any parent.
        :rtype: DecryptorV2
        """
        namespace = self
        while namespace != None:
            if namespace._decryptor != None:
                return namespace._decryptor
            namespace = namespace._parent

        return None

    def _getHandler(self):
        """
        Get the Handler set by setHandler on this or a parent Namespace node.

        :return: The Handler, or None if not set on this or any parent.
        :rtype: Namespace.Handler
        """
        namespace = self
        while namespace != None:
            if namespace._handler != None:
                return namespace._handler
            namespace = namespace._parent

        return None

    def _getMaxInterestLifetime(self):
        """
        Get the maximum Interest lifetime that was set on this or a parent node.

        :return: The maximum Interest lifetime, or the default if not set on
          this or any parent.
        :rtype: float
        """
        namespace = self
        while namespace != None:
            if namespace._maxInterestLifetime != None:
                return namespace._maxInterestLifetime
            namespace = namespace._parent

        # Return the default.
        return 16000.0

    def _getNewDataMetaInfo(self):
        """
        Get the new data MetaInfo that was set on this or a parent node.

        :return: The new data MetaInfo, or null if not set on this or any parent.
        :rtype: MetaInfo
        """
        namespace = self
        while namespace != None:
            if namespace._newDataMetaInfo != None:
                return namespace._newDataMetaInfo
            namespace = namespace._parent

        return None

    def _deserialize(self, blob, onObjectSet = None):
        """
        If _canDeserialize on the Handler of this or a parent Namespace node
        returns True, set the state to DESERIALIZING and wait for the Handler to
        call the given onDeserialized. Otherwise, just call
        _defaultOnDeserialized immediately, which sets the object and sets the
        state to OBJECT_READY. This method name has an underscore because is
        normally only called from a Handler, not from the application.

        :param Blob blob: The blob to deserialize.
        :param onObjectSet: (optional) If supplied, after setting the object,
          this calls onObjectSet(objectNamespace).
        :type onObjectSet: function object
        """
        namespace = self
        while namespace != None:
            if namespace._handler != None:
                if namespace._handler._canDeserialize(
                      self, blob, 
                      lambda obj: self._defaultOnDeserialized(obj, onObjectSet)):
                    # Wait for the Handler to set the object.
                    self._setState(NamespaceState.DESERIALIZING)
                    return

            namespace = namespace._parent

        # Debug: Check if the object has been set (even if canDeserialize returned False.)

        # Just call _defaultOnDeserialized immediately.
        self._defaultOnDeserialized(blob, onObjectSet)

    def __getitem__(self, key):
        """
        Call self.getChild(key).
        """
        if type(key) is slice:
            raise ValueError("Namespace[] does not support slices.")
        return self.getChild(key)

    def _createChild(self, component, fireCallbacks):
        """
        Create the child with the given name component and add it to this
        namespace. This private method should only be called if the child does
        not already exist. The application should use getChild.

        :param component: The name component of the child.
        :type component: Name.Component or value for the Name.Component constructor
        :param fireCallbacks: If True, call _setState to fire OnStateChanged
          callbacks for this and all parent nodes (where the initial state is
          NamespaceState.NAME_EXISTS). If False, don't call callbacks (for
          example if creating intermediate nodes).
        :return: The child Namespace object.
        :rtype: Namespace
        """
        child = Namespace(Name(self._name).append(component))
        child._parent = self
        child._root = self._root
        self._children[component] = child

        # Keep _sortedChildrenKeys synced with _children.
        bisect.insort(self._sortedChildrenKeys, component)

        if fireCallbacks:
            child._setState(NamespaceState.NAME_EXISTS)

        return child

    def _setState(self, state):
        """
        This is a private method to set the state of this Namespace object and
        to call the OnStateChanged callbacks for this and all parents. This does
        not check if this Namespace object already has the given state.

        :param int state: The new state as an int from the NamespaceState enum.
        """
        self._state = state

        # Fire callbacks.
        namespace = self
        while namespace != None:
            namespace._fireOnStateChanged(self, state)
            namespace = namespace._parent

    def _fireOnStateChanged(self, changedNamespace, state):
        # Copy the keys before iterating since callbacks can change the list.
        for id in list(self._onStateChangedCallbacks.keys()):
            # A callback on a previous pass may have removed this callback, so check.
            if id in self._onStateChangedCallbacks:
                try:
                    self._onStateChangedCallbacks[id](
                      self, changedNamespace, state, id)
                except:
                    logging.exception("Error in onStateChanged")

    def _setValidateState(self, validateState):
        """
        This is a private method to set the validate state of this Namespace
        object and to call the OnValidateStateChanged callbacks for this and all
        parents. This does not check if this Namespace object already has the
        given validate state.

        :param int validateState: The new validate state as an int from the
          NamespaceValidateState enum.
        """
        self._validateState = validateState

        # Fire callbacks.
        namespace = self
        while namespace != None:
            namespace._fireOnValidateStateChanged(self, validateState)
            namespace = namespace._parent

    def _fireOnValidateStateChanged(self, changedNamespace, validateState):
        # Copy the keys before iterating since callbacks can change the list.
        for id in list(self._onValidateStateChangedCallbacks.keys()):
            # A callback on a previous pass may have removed this callback, so check.
            if id in self._onValidateStateChangedCallbacks:
                try:
                    self._onValidateStateChangedCallbacks[id](
                      self, changedNamespace, validateState, id)
                except:
                    logging.exception("Error in onValidateStateChanged")

    def _fireOnObjectNeeded(self, neededNamespace):
        canProduce = False
        # Copy the keys before iterating since callbacks can change the list.
        for id in list(self._onObjectNeededCallbacks.keys()):
            # A callback on a previous pass may have removed this callback, so check.
            if id in self._onObjectNeededCallbacks:
                try:
                    if self._onObjectNeededCallbacks[id](self, neededNamespace, id):
                        canProduce = True
                except:
                    logging.exception("Error in onObjectNeeded")

        return canProduce

    def _defaultOnDeserialized(self, obj, onObjectSet):
        """
        Set _object to the given value, set the state to
        NamespaceState.OBJECT_READY, and fire the OnStateChanged callbacks.
        This may be called from _canDeserialize in a handler.

        :param obj: The deserialized object.
        :type obj: Blob or other type as determined by the attached handler
        :param onObjectSet: If supplied, after setting the object, this calls
          onObjectSet(object).
        :type onObjectSet: function object
        """
        self._object = obj
        self._setState(NamespaceState.OBJECT_READY)

        if onObjectSet != None:
            onObjectSet(self)

    def _onInterest(self, prefix, interest, face, interestFilterId, filter):
        """
        This is the default OnInterest callback which searches this node and
        children nodes for a matching Data packet, longest prefix. This calls
        face.putData(). If an existing Data packet is not found, add the
        Interest to the PendingIncomingInterestTable so that a later call to
        setData may satisfy it.

        :param Name prefix:
        :param Interest interest:
        :param Face face:
        :param int interestFilterId:
        :param InterestFilter filter:
        """
        interestName = interest.getName()
        if interestName.size() >= 1 and interestName[-1].isImplicitSha256Digest():
            # Strip the implicit digest.
            interestName = interestName.getPrefix(-1)

        if not self._name.isPrefixOf(interestName):
            # No match.
            return

        # Check if the Namespace node exists and has a matching Data packet.
        interestNamespace = self.getChild(interestName)
        if self.hasChild(interestName):
            bestMatch = Namespace._findBestMatchName(
              interestNamespace, interest, Common.getNowMilliseconds())
            if bestMatch != None:
                # _findBestMatchName makes sure there is a _data packet.
                face.putData(bestMatch._data)
                return

        # No Data packet found, so save the pending Interest.
        self._root._pendingIncomingInterestTable.add(interest, face)

        # Ask all OnObjectNeeded callbacks if they can produce.
        canProduce = False
        namespace = interestNamespace
        while namespace != None:
            if namespace._fireOnObjectNeeded(interestNamespace):
                canProduce = True
            namespace = namespace._parent
        if canProduce:
            interestNamespace._setState(NamespaceState.PRODUCING_OBJECT)

    @staticmethod
    def _findBestMatchName(namespace, interest, nowMilliseconds):
        """
        This is a helper for _onInterest to find the longest-prefix match under
        the given Namespace.

        :param Namespace namespace: This searches this Namespace and its children.
        :param Interest interest: This calls interest.matchesData().
        :param float nowMilliseconds: The current time in milliseconds from
          Common.getNowMilliseconds, for checking Data packet freshness.
        :return: The Namespace object for the matched name or None if not found.
        :rtype: Namespace
        """
        bestMatch = None

        # Search the children backwards which will result in a "less than" name
        # among names of the same length.
        for i in range(len(namespace._sortedChildrenKeys) - 1, -1, -1):
            child = namespace._children[namespace._sortedChildrenKeys[i]]
            childBestMatch = Namespace._findBestMatchName(
              child, interest, nowMilliseconds)

            if (childBestMatch != None and
                (bestMatch == None or
                 childBestMatch.name.size() >= bestMatch.name.size())):
                bestMatch = childBestMatch

        if bestMatch != None:
            # We have a child match, and it is longer than this name, so return it.
            return bestMatch

        if (interest.getMustBeFresh() and
            namespace._freshnessExpiryTimeMilliseconds != None and
            nowMilliseconds >= namespace._freshnessExpiryTimeMilliseconds):
            # The Data packet is no longer fresh.
            # Debug: When to set the state to OBJECT_READY_BUT_STALE?
            return None

        if namespace._data != None and interest.matchesData(namespace._data):
            return namespace

        return None

    def _onData(self, interest, data):
        dataNamespace = self[data.name]
        if not dataNamespace.setData(data):
            # A Data packet is already attached.
            return
        self._setState(NamespaceState.DATA_RECEIVED)

        # TODO: Start the validator.
        dataNamespace._setValidateState(NamespaceValidateState.VALIDATING)

        decryptor = dataNamespace._getDecryptor()
        if decryptor == None:
            dataNamespace._deserialize(data.content, None)
            return

        # Decrypt, then deserialize.
        dataNamespace._setState(NamespaceState.DECRYPTING)
        try:
            encryptedContent = EncryptedContent()
            encryptedContent.wireDecodeV2(data.content)
        except Exception as ex:
            dataNamespace._decryptionError = (
              "Error decoding the EncryptedContent: " + repr(ex))
            dataNamespace._setState(NamespaceState.DECRYPTION_ERROR)
            return

        def onError(code, message):
            dataNamespace._decryptionError = (
              "Decryptor error " + repr(code) + ": " + message)
            dataNamespace._setState(NamespaceState.DECRYPTION_ERROR)
        decryptor.decrypt(encryptedContent, dataNamespace._deserialize, onError)

    @staticmethod
    def getNextCallbackId():
        """
        Get the next unique callback ID. This uses a threading.Lock() to be
        thread safe. This is an internal method only meant to be called by
        library classes; the application should not call it.

        :return: The next callback ID.
        :rtype: int
        """
        with Namespace._lastCallbackIdLock:
            Namespace._lastCallbackId += 1
            return Namespace._lastCallbackId

    name = property(getName)
    parent = property(getParent)
    root = property(getRoot)
    state = property(getState)
    validateState = property(getValidateState)
    validationError = property(getValidationError)
    decryptionError = property(getDecryptionError)
    signingError = property(getSigningError)
    data = property(getData)
    # object is a special Python term, so use obj .
    obj = property(getObject)

    _lastCallbackId = 0
    _lastCallbackIdLock = threading.Lock()

class NamespaceState(object):
    """
    A NamespaceState specifies the state of a Namespace node.
    """
    NAME_EXISTS =             0
    INTEREST_EXPRESSED =      1
    INTEREST_TIMEOUT =        2
    INTEREST_NETWORK_NACK =   3
    DATA_RECEIVED =           4
    DESERIALIZING =           5
    DECRYPTING =              6
    DECRYPTION_ERROR =        7
    PRODUCING_OBJECT =        8
    SERIALIZING =             9
    ENCRYPTING =             10
    ENCRYPTION_ERROR =       11
    SIGNING =                12
    SIGNING_ERROR =          13
    OBJECT_READY =           14
    OBJECT_READY_BUT_STALE = 15

class NamespaceValidateState(object):
    """
    A NamespaceValidateState specifies the state of validating a Namespace node.
    """
    WAITING_FOR_DATA = 0
    VALIDATING =       1
    VALIDATE_SUCCESS = 2
    VALIDATE_FAILURE = 3
