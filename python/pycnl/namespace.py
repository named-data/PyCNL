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
Namespace is the main class which represents the name tree and related
operations to manage it.
"""

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

    def getName(self):
        """
        Get the name of this node in the name tree. This includes the name
        components of parent nodes. To the name component of just this node,
        use getName()[-1].

        :return: The name of this namespace.
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
        Get the child with the given name component, creating it if needed.

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
            child = Namespace(Name(self._name).append(component))
            child._parent = self
            self._children[component] = child
            return child

    def getChildComponents(self):
        """
        Get a list of the name component of all child nodes.

        :return: A fresh sorted list of the name component of all child nodes.
          This remains the same if child nodes are added or deleted.
        :rtype: list of Name.Component
        """
        result = []
        for key in self._children.keys():
            result.append(key)

        result.sort()
        return result

    def __getitem__(self, key):
        """
        Call self.getChild(key).
        """
        if type(key) is slice:
            raise ValueError("Namespace[] does not support slices.")
        return self.getChild(key)

    name = property(getName)
    parent = property(getParent)
    