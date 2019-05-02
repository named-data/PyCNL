# -*- Mode:python; c-file-style:"gnu"; indent-tabs-mode:nil -*- */
#
# Copyright (C) 2018-2019 Regents of the University of California.
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
This module defines the ContentMetaInfo class which represents the information in
the _meta packet of a Generalized Object.
"""

# This module is produced by: protoc --python_out=. content-meta-info.proto
from pycnl.generalized_object.content_meta_info_pb2 import ContentMetaInfoMessage
from pyndn.encoding import ProtobufTlv
from pyndn.util import Blob
from pyndn.util.common import Common

class ContentMetaInfo(object):
    """
    Create a new ContentMetaInfo object, possibly copying values from another
    object.

    :param ContentMetaInfo value: (optional) If value is a ContentMetaInfo, copy
      its values. If value is omitted, set all the fields to their default
      unspecified values.
    """
    def __init__(self, value = None):
        if value == None:
            self.clear()
        elif isinstance(value, ContentMetaInfo):
            # Copy its values.
            self._contentType = value._contentType
            self._timestamp = value._timestamp
            self._hasSegments = value._hasSegments
            self._other = value._other
        else:
            raise RuntimeError(
              "Unrecognized type for ContentMetaInfo constructor: " +
              str(type(value)))

    def getContentType(self):
        """
        Get the content type.

        :return: The content type. If not specified, return an empty string.
        :rtype: str
        """
        return self._contentType

    def getTimestamp(self):
        """
        Get the time stamp.

        :return: The time stamp as milliseconds since Jan 1, 1970 UTC. If not
          specified, return None.
        :rtype: float
        """
        return self._timestamp

    def getHasSegments(self):
        """
        Get the hasSegments flag.

        :return: The hasSegments flag.
        :rtype: bool
        """
        return self._hasSegments

    def getOther(self):
        """
        Get the Blob containing the optional other info.

        :return: The other info. If not specified, return an isNull Blob.
        :rtype: Blob
        """
        return self._other

    def setContentType(self, contentType):
        """
        Set the content type.

        :param str contentType: The content type.
        :return: This ContentMetaInfo so that you can chain calls to update
          values.
        :rtype: ContentMetaInfo
        """
        self._contentType = contentType
        return self

    def setTimestamp(self, timestamp):
        """
        Set the time stamp.

        :param float timestamp: The time stamp.
        :return: This ContentMetaInfo so that you can chain calls to update
          values.
        :rtype: ContentMetaInfo
        """
        self._timestamp = Common.nonNegativeFloatOrNone(timestamp)
        return self

    def setHasSegments(self, hasSegments):
        """
        Set the hasSegments flag.

        :param bool hasSegments: The hasSegments flag.
        :return: This ContentMetaInfo so that you can chain calls to update
          values.
        :rtype: ContentMetaInfo
        """
        self._hasSegments = hasSegments
        return self

    def setOther(self, other):
        """
        Set the Blob containing the optional other info.

        :param Blob other: The other info, or a default null Blob() if not
          specified.
        :return: This ContentMetaInfo so that you can chain calls to update
          values.
        :rtype: ContentMetaInfo
        """
        self._other = other if isinstance(other, Blob) else Blob(other)
        return self

    def clear(self):
        """
        Set all the fields to their default unspecified values.
        """
        self._contentType = ""
        self._timestamp = None
        self._hasSegments = False
        self._other = Blob()

    def wireEncode(self):
        """
        Encode this ContentMetaInfo.

        :return: The encoding Blob.
        :rtype: Blob
        """
        if self._timestamp == None:
            raise RuntimeError("The ContentMetaInfo timestamp is not specified")

        meta = ContentMetaInfoMessage()
        meta.content_meta_info.content_type = self._contentType
        meta.content_meta_info.timestamp = int(round(self._timestamp))
        meta.content_meta_info.has_segments = self._hasSegments
        if not self._other.isNull() and self._other.size() > 0:
            meta.content_meta_info.other = self._other.toBytes()

        return ProtobufTlv.encode(meta)

    def wireDecode(self, input):
        """
        Decode the input and update this ContentMetaInfo.

        :param input: The array with the bytes to decode.
        :type input: An array type with int elements
        """
        meta = ContentMetaInfoMessage()
        ProtobufTlv.decode(meta, input)

        self.clear()
        self._contentType = meta.content_meta_info.content_type
        self._timestamp = float(meta.content_meta_info.timestamp)
        self._hasSegments = meta.content_meta_info.has_segments
        if len(meta.content_meta_info.other) > 0:
            self._other = Blob(bytearray(meta.content_meta_info.other), False)

    # Create managed properties for read/write properties of the class for more pythonic syntax.
    contentType = property(getContentType, setContentType)
    timestamp = property(getTimestamp, setTimestamp)
    hasSegments = property(getHasSegments, setHasSegments)
    other = property(getOther, setOther)
