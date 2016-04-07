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
        self._face = None
        # The dictionary key is the callback ID. The value is the onNameAdded function.
        self._onNameAddedCallbacks = {}
        # The dictionary key is the callback ID. The value is the onDataSet function.
        self._onDataSetCallbacks = {}

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

    def getChild(self, component):
        """
        Get the child with the given name component, creating it if needed. This
        is equivalent to namespace[component].

        :param component: The name component of the child.
        :type component: Name.Component or value for the Name.Component constructor
        :return: The child Namespace object.
        :rtype: Namespace
        """
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
        Find or create the Namespace object whose name equals the Data packet
        name and attach the Data packet to that "dataNamespace". If a Data
        packet is already attached to the dataNamespace, do nothing. If the name
        of this Namespace is a prefix of the Data packet name, then this finds
        or creates child Namespace nodes as needed. If not a prefix, then this
        will search parent nodes as needed. So in theory it doesn't matter which
        Namespace node you call setData but it is more efficient to call setData
        on the closest node.

        :param Data data: The Data packet object whose name is the name in this
          Namespace. For efficiency, this does not copy the Data packet object.
          If your application may change the object later, then you must call
          setData with a copy of the object.
        :raises RuntimeError: If the name of the root Namespace node is not a 
          prefix of the Data packet name (so that it is not possible to create
          any children to match the Data name).
        """
        # Find the starting Namespace to which we may have to add children.
        dataNamespace = self
        while not dataNamespace._name.isPrefixOf(data.name):
            dataNamespace = dataNamespace._parent
            if dataNamespace == None:
                raise RuntimeError(
                  "The root Namespace name must be a prefix of the Data packet name")

        # Find or create the child node whose name equals the data name. We know
        # startingNamespace is a prefix, so we can just go by component count
        # instead of a full compare.
        while dataNamespace._name.size() < data.name.size():
            nextComponent = data.name[dataNamespace._name.size()]
            dataNamespace = dataNamespace[nextComponent]

        if dataNamespace._data != None:
            # We already have an attached object.
            return
        dataNamespace._data = data

        # Fire callbacks.
        namespace = dataNamespace
        while namespace:
            namespace._fireOnDataSet(dataNamespace)
            namespace = namespace._parent

    def getData(self):
        """
        Get the Data packet attached to this Namespace object.

        :return: The Data packet object, or None if not set.
        :rtype: Data
        """
        return self._data

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

    def addOnDataSet(self, onDataSet):
        """
        Add an onDataSet callback. When a Data packet is attached to this
        Namespace node or any children, this calls onDataSet as described below.

        :param onDataSet: This calls
          onDataSet(namespace, dataNamespace, callbackId)
          where namespace is this Namespace, addedToNamespace is the Namespace
          to which the Data packet was attached, and callbackId is the callback
          ID returned by this method. To get the data packet, use
          dataNamespace.getData().
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        :type onDataSet: function object
        :return: The callback ID which you can use in removeCallback().
        :rtype: int
        """
        callbackId = Namespace.getNextCallbackId()
        self._onDataSetCallbacks[callbackId] = onDataSet
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
        addOnDataSet (or check getData() later). This uses ExponentialReExpress
        to re-express a timed-out interest with longer lifetimes.
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
            self.setData(data)

        if interestTemplate == None:
            interestTemplate = Interest()
            interestTemplate.setInterestLifetimeMilliseconds(4000)
        face.expressInterest(
          self._name, interestTemplate, onData,
          ExponentialReExpress.makeOnTimeout(face, onData, None))

    def _getFace(self):
        namespace = self
        while namespace != None:
            if namespace._face != None:
                return namespace._face
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
        self._onDataSetCallbacks.pop(callbackId, None)

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

    def _fireOnDataSet(self, dataNamespace):
        # Copy the keys before iterating since callbacks can change the list.
        for id in list(self._onDataSetCallbacks.keys()):
            # A callback on a previous pass may have removed this callback, so check.
            if id in self._onDataSetCallbacks:
                try:
                    self._onDataSetCallbacks[id](self, dataNamespace, id)
                except:
                    logging.exception("Error in onDataSet")

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

    _lastCallbackId = 0
    _lastCallbackIdLock = threading.Lock()
