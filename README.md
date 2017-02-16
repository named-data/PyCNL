PyCNL: An NDN Common Name Library for Python
============================================

The Common Name Library (CNL) is a proposed API for NDN applications. Built on
top of the lower-level Interest/Data exchange primitives of the Common Client
Libraries, the CNL maintains an abstraction of the application's namespace. The
application can attach specialized handlers to nodes of the namespace, for
example to treat part of the name tree as segmented content, or to do data
encryption/decryption. The CNL can also alert the application when new names are
added to the namespace or when content is attached to a namespace node, whether
by receiving a Data packet from the network, retrieving from a repo, or
assembling the result of segmented content.


License
-------
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
A copy of the GNU Lesser General Public License is in the file COPYING.
