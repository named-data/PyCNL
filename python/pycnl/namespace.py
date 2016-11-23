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
This module defines the Namespace class which is the main class that represents
the name tree and related operations to manage it.
"""

import bisect
import threading
import logging
from pyndn import Name, Interest
from pyndn.util import ExponentialReExpress

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
        self._data = None
        self._content = None
        self._face = None
        # The dictionary key is the callback ID. The value is the onNameAdded function.
        self._onNameAddedCallbacks = {}
        # The dictionary key is the callback ID. The value is the onContentSet function.
        self._onContentSetCallbacks = {}
        self._transformContent = None

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

    def hasChild(self, component):
        """
        Check if this node in the namespace has the given child.

        :param component: The name component of the child.
        :type component: Name.Component or value for the Name.Component constructor
        :return: True if this has a child with the name component.
        :rtype: bool
        """
        if not isinstance(component, Name.Component):
            component = Name.Component(component)

        return component in self._children

    def getChild(self, nameOrComponent):
        """
        Get a child (or descendant), creating it if needed. This is equivalent
        to namespace[component]. If a child is created, this calls callbacks as
        described by addOnNameAdded,

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
                descendantNamespace = descendantNamespace[nextComponent]

            return descendantNamespace
        else:
            component = nameOrComponent
            if not isinstance(component, Name.Component):
                component = Name.Component(component)

            if component in self._children:
                return self._children[component]
            else:
                return self._createChild(component)

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
        Attach the Data packet to this Namespace. This calls callbacks as
        described by addOnContentSet. If a Data packet is already attached, do
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

        transformContent = self._getTransformContent()
        # TODO: TransformContent should take an OnError.
        if transformContent != None:
            transformContent(data, self._onContentTransformed)
        else:
            # Otherwise just invoke directly.
            self._onContentTransformed(data, data.content)

    def getData(self):
        """
        Get the Data packet attached to this Namespace object. Note that
        getContent() may be different than the content in the attached Data
        packet (for example if the content is decrypted). To get the content,
        you should use getContent() instead of getData().getContent(). Also,
        the Data packet name is the same as the name of this Namespace node,
        so you can simply use getName() instead of getData().getName(). You
        should only use getData() to get other information such as the MetaInfo.

        :return: The Data packet object, or None if not set.
        :rtype: Data
        """
        return self._data

    def getContent(self):
        """
        Get the content attached to this Namespace object. Note that
        getContent() may be different than the content in the attached Data
        packet (for example if the content is decrypted).

        :return: The content Blob, or None if not set.
        :rtype: Blob
        """
        return self._content

    def addOnNameAdded(self, onNameAdded):
        """
        Add an onNameAdded callback. When a new name is added to this namespace
        at this node or any children, this calls onNameAdded as described below.

        :param onNameAdded: This calls
          onNameAdded(namespace, addedNamespace, callbackId)
          where namespace is this Namespace, addedNamespace is the Namespace of
          the added name, and callbackId is the callback ID returned by this
          method.
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        :type onNameAdded: function object
        :return: The callback ID which you can use in removeCallback().
        :rtype: int
        """
        callbackId = Namespace.getNextCallbackId()
        self._onNameAddedCallbacks[callbackId] = onNameAdded
        return callbackId

    def addOnContentSet(self, onContentSet):
        """
        Add an onContentSet callback. When the content has been set for this
        Namespace node or any children and , this calls onContentSet as
        described below.

        :param onContentSet: This calls
          onContentSet(namespace, contentNamespace, callbackId)
          where namespace is this Namespace, contentNamespace is the Namespace
          where the content was set, and callbackId is the callback ID returned
          by this method. If you only care if the content has been set for this
          Namespace (and not any of its children) then your callback can check
          "if contentNamespace == namespace". To get the content or data packet,
          use contentNamespace.getContent() or contentNamespace.getData().
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        :type onContentSet: function object
        :return: The callback ID which you can use in removeCallback().
        :rtype: int
        """
        callbackId = Namespace.getNextCallbackId()
        self._onContentSetCallbacks[callbackId] = onContentSet
        return callbackId

    def setFace(self, face):
        """
        Set the Face used when expressInterest is called on this or child nodes
        (unless a child node has a different Face).
        TODO: Replace this by a mechanism for requesting a Data object which is
        more general than a Face network operation.

        :param Face face: The Face object. If this Namespace object already has
        a Face object, it is replaced.
        """
        self._face = face

    def expressInterest(self, interestTemplate = None):
        """
        Call expressInterest on this (or a parent's) Face where the interest
        name is the name of this Namespace node. When the Data packet is
        received this calls setData, so you should use a callback with
        addOnContentSet. This uses ExponentialReExpress to re-express a timed-out
        interest with longer lifetimes.
        TODO: How to alert the application on a final interest timeout?
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

        def onData(interest, data):
            self[data.name].setData(data)

        if interestTemplate == None:
            interestTemplate = Interest()
            interestTemplate.setInterestLifetimeMilliseconds(4000)
        face.expressInterest(
          self._name, interestTemplate, onData,
          ExponentialReExpress.makeOnTimeout(face, onData, None))

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

    def removeCallback(self, callbackId):
        """
        Remove the callback with the given callbackId. This does not search for
        the callbackId in child nodes. If the callbackId isn't found, do nothing.

        :param int callbackId: The callback ID returned, for example, from
          addOnNameAdded.
        """
        self._onNameAddedCallbacks.pop(callbackId, None)
        self._onContentSetCallbacks.pop(callbackId, None)

    def __getitem__(self, key):
        """
        Call self.getChild(key).
        """
        if type(key) is slice:
            raise ValueError("Namespace[] does not support slices.")
        return self.getChild(key)

    def _createChild(self, component):
        """
        Create the child with the given name component and add it to this
        namespace. This private method should only be called if the child does
        not already exist. The application should use getChild.

        :param component: The name component of the child.
        :type component: Name.Component or value for the Name.Component constructor
        :return: The child Namespace object.
        :rtype: Namespace
        """
        child = Namespace(Name(self._name).append(component))
        child._parent = self
        self._children[component] = child

        # Keep _sortedChildrenKeys synced with _children.
        bisect.insort(self._sortedChildrenKeys, component)

        # Fire callbacks.
        namespace = self
        while namespace:
            namespace._fireOnNameAdded(child)
            namespace = namespace._parent

        return child

    def _fireOnNameAdded(self, addedNamespace):
        # Copy the keys before iterating since callbacks can change the list.
        for id in list(self._onNameAddedCallbacks.keys()):
            # A callback on a previous pass may have removed this callback, so check.
            if id in self._onNameAddedCallbacks:
                try:
                    self._onNameAddedCallbacks[id](self, addedNamespace, id)
                except:
                    logging.exception("Error in onNameAdded")

    def _onContentTransformed(self, data, content):
        """
        Set _data and _content to the given values and fire the OnContentSet
        callbacks. This may be called from a _transformContent handler invoked
        by setData.

        :param Data data: The Data packet object given to setData.
        :param Blob content: The content which may have been processed from the
          Data packet, e.g. by decrypting.
        """
        self._data = data
        self._content = content

        # Fire callbacks.
        namespace = self
        while namespace:
            namespace._fireOnContentSet(self)
            namespace = namespace._parent

    def _fireOnContentSet(self, contentNamespace):
        # Copy the keys before iterating since callbacks can change the list.
        for id in list(self._onContentSetCallbacks.keys()):
            # A callback on a previous pass may have removed this callback, so check.
            if id in self._onContentSetCallbacks:
                try:
                    self._onContentSetCallbacks[id](self, contentNamespace, id)
                except:
                    logging.exception("Error in onContentSet")

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
    data = property(getData)
    content = property(getContent)

    _lastCallbackId = 0
    _lastCallbackIdLock = threading.Lock()
