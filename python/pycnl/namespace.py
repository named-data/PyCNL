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
from pyndn import Name, Interest
from pyndn.util import ExponentialReExpress
from pycnl.impl.pending_incoming_interest_table import PendingIncomingInterestTable

class Namespace(object):
    def __init__(self, name):
        """
        Create a Namespace object with the given name, and with no parent. This
        is the root of the name tree. To create child nodes, use
        myNamespace.getChild("foo") or myNamespace["foo"].

        :param Name name: The name of this root node in the namespace. This
          makes a copy of the name.
        """
        self._name = Name(name)
        self._parent = None
        # The dictionary key is a Name.Component. The value is the child Namespace.
        self._children = {}
        # The keys of _children in sorted order, kept in sync with _children.
        # (We don't use OrderedDict because it doesn't sort keys on insert.)
        self._sortedChildrenKeys = []
        self._state = NamespaceState.NAME_EXISTS
        self._networkNack = None
        self._validateState = NamespaceValidateState.WAITING_FOR_DATA
        self._validationError = None
        self._data = None
        self._content = None
        self._face = None
        # The dictionary key is the callback ID. The value is the onStateChanged function.
        self._onStateChangedCallbacks = {}
        # The dictionary key is the callback ID. The value is the onValidateStateChanged function.
        self._onValidateStateChangedCallbacks = {}
        self._transformContent = None
        # setFace will create this in the root Namespace node.
        self._pendingIncomingInterestTable = None

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
        result = self
        while result._parent:
            result = result._parent
        return result

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
        first created, its state is NamespaceValidateState.WAITING_FOR_DATA .

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

    def setData(self, data):
        """
        Attach the Data packet to this Namespace. This sets the state to
        NamespaceState.DATA_RECEIVED and calls callbacks as described by
        addOnStateChanged. However, if a Data packet is already attached, do
        nothing.

        :param Data data: The Data packet object whose name must equal the name
          in this Namespace node. To get the right Namespace, you can use
          getChild(data.getName()). For efficiency, this does not copy the Data
          packet object. If your application may change the object later, then
          you must call setData with a copy of the object.
        :raises RuntimeError: If the Data packet name does not equal the name of
          this Namespace node.
        """
        if self._data != None:
            # We already have an attached object.
            return
        if not data.name.equals(self._name):
            raise RuntimeError(
              "The Data packet name does not equal the name of this Namespace node.")

        root = self.getRoot()
        if root._pendingIncomingInterestTable != None:
            # Quickly send the Data packet to satisfy interest, before calling callbacks.
            root._pendingIncomingInterestTable.satisfyInterests(data)

        self._data = data
        self._setState(NamespaceState.DATA_RECEIVED)

    def getData(self):
        """
        Get the Data packet attached to this Namespace object. Note that
        getContent() may be different than the content in the attached Data
        packet (for example if the content is decrypted). To get the content,
        you should use getContent() instead of getData().getContent(). Also,
        the Data packet name is the same as the name of this Namespace node,
        so you can simply use getName() instead of getData().getName(). You
        should only use getData() to get other information such as the MetaInfo.
        (It is possible that this Namespace object has an attacked Data packet,
        but getContent() is still None because this state has not yet changed
        to NamespaceState.CONTENT_READY.)

        :return: The Data packet object, or None if not set.
        :rtype: Data
        """
        return self._data

    def getContent(self):
        """
        Get the content attached to this Namespace object. Note that
        getContent() may be different than the content in the attached Data
        packet (for example if the content is decrypted). In the default
        behavior, the content is the Blob content of the Data packet, but may be
        a different type as determined by the attached handler.

        :return: The content which is a Blob or other type as determined by the
           attached handler. You must cast to the correct type. If the content
           is not set, return None.
        :rtype: Blob or other type as determined by the attached handler
        """
        return self._content

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
          onValidateStateChanged(namespace, changedNamespace, state, callbackId)
          where namespace is this Namespace, changedNamespace is the Namespace
          (possibly a child) whose validate state has changed, state is the new
          state as an int from the NamespaceValidateState enum, and callbackId
          is the callback ID returned by this method. If you only care if the
          state has changed for this Namespace (and not any of its children)
          then your callback can check "if changedNamespace == namespace". (Note
          that the state given to the callback may be different than
          changedNamespace.getValidateState() if other processing has changed
          the state before this callback is called.)
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
          regixter prefix fails for any reason, this calls
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
            root = self.getRoot()
            if root._pendingIncomingInterestTable == None:
                # All _onInterest callbacks share this in the root node.
                # When we add a new data packet to a Namespace node, we will
                # also check if it satisfies a pending interest.
                root._pendingIncomingInterestTable = PendingIncomingInterestTable()

            face.registerPrefix(
              self._name, self._onInterest, onRegisterFailed, onRegisterSuccess)

    def expressInterest(self, interestTemplate = None):
        """
        Call expressInterest on this (or a parent's) Face where the interest
        name is the name of this Namespace node. When the Data packet is
        received this calls setData, so you should use a callback with
        addOnStateChanged. This uses ExponentialReExpress to re-express a
        timed-out interest with longer lifetimes. If the Interest times out,
        this sets the state to NamespaceState.INTEREST_TIMEOUT and calls the
        OnStateChanged callbacks. If this receives a network Nack, this stores
        the NetworkNack object which you can access with getNetworkNack(), sets
        the state to NamespaceState.INTEREST_NETWORK_NACK, and calls the
        OnStateChanged callbacks.
        TODO: Replace this by a mechanism for requesting a Data object which is
        more general than a Face network operation.
        :raises RuntimeError: If a Face object has not been set for this or a
          parent Namespace node.

        :param Interest interestTemplate: (optional) The interest template for
          expressInterest. If omitted, just use a default interest lifetime.
        """
        face = self._getFace()
        if face == None:
            raise ValueError("A Face object has not been set for this or a parent.")

        # TODO: What if the state is already INTEREST_EXPRESSED?
        self._setState(NamespaceState.INTEREST_EXPRESSED)

        def onData(interest, data):
            dataNamespace = self[data.name]
            # setData will set the state to DATA_RECEIVED.
            dataNamespace.setData(data)

            # TODO: Start the validator.
            dataNamespace._setValidateState(NamespaceValidateState.VALIDATING)

            transformContent = dataNamespace._getTransformContent()
            # TODO: TransformContent should take an OnError.
            if transformContent != None:
                transformContent(data, dataNamespace._onContentTransformed)
            else:
                # Otherwise just invoke directly.
                dataNamespace._onContentTransformed(data.content)

        def onTimeout(interest):
            self._setState(NamespaceState.INTEREST_TIMEOUT)

        def onNetworkNack(interest, networkNack):
            self._networkNack = networkNack
            self._setState(NamespaceState.INTEREST_NETWORK_NACK)

        if interestTemplate == None:
            interestTemplate = Interest()
            interestTemplate.setInterestLifetimeMilliseconds(4000)
        face.expressInterest(
          self._name, interestTemplate, onData,
          ExponentialReExpress.makeOnTimeout(face, onData, onTimeout),
          onNetworkNack)

    def _getFace(self):
        """
        Get the Face set by setFace on this or a parent Namespace node.

        :return: The Face, or None if not set on this or any parent.
        :rtype: Face
        """
        namespace = self
        while namespace != None:
            if namespace._face != None:
                return namespace._face
            namespace = namespace._parent

        return None

    def _getTransformContent(self):
        """
        Get the TransformContent callback on this or a parent Namespace node.

        :return: The TransformContent callback, or None if not set on this or
          any parent.
        :rtype: function object
        """
        namespace = self
        while namespace != None:
            if namespace._transformContent != None:
                return namespace._transformContent
            namespace = namespace._parent

        return None

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
        not check if the state already has the given state.

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

    def _setValidateState(self, state):
        """
        This is a private method to set the validate state of this Namespace
        object and to call the OnValidateStateChanged callbacks for this and all
        parents. This does not check if the state already has the given state.

        :param int state: The new state as an int from the
          NamespaceValidateState enum.
        """
        self._validateState = state

        # Fire callbacks.
        namespace = self
        while namespace != None:
            namespace._fireOnValidateStateChanged(self, state)
            namespace = namespace._parent

    def _fireOnValidateStateChanged(self, changedNamespace, state):
        # Copy the keys before iterating since callbacks can change the list.
        for id in list(self._onValidateStateChangedCallbacks.keys()):
            # A callback on a previous pass may have removed this callback, so check.
            if id in self._onValidateStateChangedCallbacks:
                try:
                    self._onValidateStateChangedCallbacks[id](
                      self, changedNamespace, state, id)
                except:
                    logging.exception("Error in onValidateStateChanged")

    def _onContentTransformed(self, content):
        """
        Set _content to the given value, set the state to
        NamespaceState.CONTENT_READY, and fire the OnStateChanged callbacks.
        This may be called from a _transformContent handler.

        :param content: The content which may have been processed from the
          Data packet, e.g. by decrypting.
        :type content: Blob or other type as determined by the attached handler
        """
        self._content = content
        self._setState(NamespaceState.CONTENT_READY)

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
        if self.hasChild(interestName):
            bestMatch = Namespace._findBestMatchName(self[interestName], interest)
            if bestMatch != None:
                # _findBestMatchName makes sure there is a _data packet.
                face.putData(self[bestMatch]._data)
                return

        # No Data packet found, so save the pending Interest.
        self.getRoot()._pendingIncomingInterestTable.add(interest, face)
        # Signal that a Data packet is needed.
        # Debug should it be a different state from INTEREST_EXPRESSED?
        self.getChild(interestName)._setState(NamespaceState.INTEREST_EXPRESSED)

    @staticmethod
    def _findBestMatchName(namespace, interest):
        """
        This is a helper for _onInterest to find the longest-prefix match under
        the Namespace.

        :param Namespace namespace: This searches this Namespace and its children.
        :param Interest interest: This calls interest.matchesData().
        :return: The matched Name of None if not found.
        :rtype: Name
        """
        bestMatch = None
        # Search the children backwards which will result in a "less than" name
        # among names of the same length.
        for i in range(len(namespace._sortedChildrenKeys) - 1, -1, -1):
            child = namespace._children[namespace._sortedChildrenKeys[i]]
            childBestMatch = Namespace._findBestMatchName(child, interest)

            if (childBestMatch != None and
                (bestMatch == None or childBestMatch.size() >= bestMatch.size())):
                bestMatch = childBestMatch

        if bestMatch != None:
            # We have a child match, and it is longer than this name, so return it.
            return bestMatch

        # TODO: Check childSelector.
        if namespace._data != None and interest.matchesData(namespace._data):
            return namespace._name

        return None

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
    state = property(getState)
    validateState = property(getValidateState)
    data = property(getData)
    content = property(getContent)

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
    DECRYPTING =              5
    DECRYPTION_ERROR =        6
    TRANSFORMING_CONTENT =    7
    CONTENT_READY =           8
    CONTENT_READY_BUT_STALE = 9

class NamespaceValidateState(object):
    """
    A NamespaceValidateState specifies the state of validating a Namespace node.
    """
    WAITING_FOR_DATA = 0
    VALIDATING =       1
    VALIDATE_SUCCESS = 2
    VALIDATE_FAILURE = 3
