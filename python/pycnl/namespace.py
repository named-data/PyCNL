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
from pyndn.util import Name

class Namespace(object):
    def __init__(self, name):
        """
        Create a Namespace object with the given name, and with no parent. This
        is the top of the name tree. To create child nodes, use
        myNamespace.getChild("foo") or myNamespace["foo"].

        :param Name name: The name of this top-level node in the namespace. This
          makes a copy of the name.
        """
        self._name = Name(name)
        self._parent = None
        # The dictionary key is a Name.Component. The value is the child Namespace.
        self._children = {}
        # The keys of _children in sorted order, kept in sync with _children.
        # (We don't use OrderedDict because it doesn't sort keys on insert.)
        self._sortedChildrenKeys = []
        # The dictionary key is the callback ID. The value is the onNameAdded function.
        self._onNameAddedCallbacks = {}

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

        :return: The parent namespace, or None if this is the top of the tree.
        :rtype: Namespace
        """
        return self._parent

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

    def addOnNameAdded(self, onNameAdded):
        """
        Add an onNameAdded callback. When a new name is added to this namespace
        at this node or any children, this calls
        onNameAdded(namespace, addedNamespace, callbackId) as described below.

        :param onNameAdded: This calls
          onNameAdded(namespace, addedNamespace, callbackId)
          where namespace is this Namespace, addedNamespace is the Namespace of
          the added name, and callbackId is the callback ID returned by this
          method.
          NOTE: The library will log any exceptions raised by this callback, but
          for better error handling the callback should catch and properly
          handle any exceptions.
        :type onComplete: function object
        :return: The callback ID which you can use in removeCallback().
        :rtype: int
        """
        callbackId = Namespace.getNextCallbackId()
        self._onNameAddedCallbacks[callbackId] = onNameAdded
        return callbackId

    def removeCallback(self, callbackId):
        """
        Remove the callback with the given callbackId. This does not search for
        the callbackId in child nodes. If the callbackId isn't found, do nothing.

        :param int callbackId: The callback ID returned, for example, from
          addOnNameAdded.
        """
        self._onNameAddedCallbacks.pop(callbackId, None)

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
        namespace. This is a private method should only be called if the child
        does not already exist. The application should use getChild.

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
        name = child.getName()
        namespace = self
        while namespace:
            namespace._fireOnNameAdded(child)
            namespace = namespace._parent

        return child

    def _fireOnNameAdded(self, addedNamespace):
        for id in self._onNameAddedCallbacks:
            try:
                self._onNameAddedCallbacks[id](self, addedNamespace, id)
            except:
                logging.exception("Error in onNameAdded")

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

    _lastCallbackId = 0
    _lastCallbackIdLock = threading.Lock()
