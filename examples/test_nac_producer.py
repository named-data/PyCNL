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
This registers with the local NFD to produce pre-encrypted test data for
test_nac_consumer (which must be run separately).
"""

import time
from pyndn import Name, Data, Face
from pyndn.util import Blob
from pyndn.encrypt.algo import EncryptParams, EncryptAlgorithmType
from pyndn.encrypt.algo import Encryptor, RsaAlgorithm
from pyndn.security import KeyType, KeyChain, RsaKeyParams
from pyndn.security.identity import IdentityManager
from pyndn.security.identity import MemoryIdentityStorage, MemoryPrivateKeyStorage
from pyndn.security.policy import NoVerifyPolicyManager

DATA_CONTENT = bytearray([
    # "This test message was decrypted."
    0x54, 0x68, 0x69, 0x73, 0x20, 0x74, 0x65, 0x73,
    0x74, 0x20, 0x6d, 0x65, 0x73, 0x73, 0x61, 0x67,
    0x65, 0x20, 0x77, 0x61, 0x73, 0x20, 0x64, 0x65,
    0x63, 0x72, 0x79, 0x70, 0x74, 0x65, 0x64, 0x2e
])

AES_KEY = bytearray([
    0xdd, 0x60, 0x77, 0xec, 0xa9, 0x6b, 0x23, 0x1b,
    0x40, 0x6b, 0x5a, 0xf8, 0x7d, 0x3d, 0x55, 0x32
])

INITIAL_VECTOR = bytearray([
    0x73, 0x6f, 0x6d, 0x65, 0x72, 0x61, 0x6e, 0x64,
    0x6f, 0x6d, 0x76, 0x65, 0x63, 0x74, 0x6f, 0x72
])

DEFAULT_RSA_PUBLIC_KEY_DER = bytearray([
    0x30, 0x82, 0x01, 0x22, 0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01,
    0x01, 0x05, 0x00, 0x03, 0x82, 0x01, 0x0f, 0x00, 0x30, 0x82, 0x01, 0x0a, 0x02, 0x82, 0x01, 0x01,
    0x00, 0xd4, 0x4f, 0xd9, 0xae, 0x7a, 0xd2, 0x87, 0x80, 0x67, 0x11, 0x31, 0xb8, 0x5b, 0xac, 0x8b,
    0x5f, 0xf2, 0x21, 0x28, 0x2c, 0x70, 0xec, 0x66, 0xe9, 0x18, 0xee, 0x5e, 0xf1, 0xe3, 0xef, 0x09,
    0xcb, 0x5e, 0xe0, 0xcd, 0xe4, 0x39, 0x6a, 0x3f, 0x43, 0x2a, 0x3e, 0x1a, 0x06, 0xf2, 0xcc, 0xb0,
    0x0f, 0x5b, 0xd8, 0xa1, 0x3f, 0x1c, 0xb8, 0xfa, 0x8c, 0xa4, 0xbf, 0xa0, 0x57, 0x61, 0xcb, 0x35,
    0xa9, 0x0f, 0x56, 0x76, 0x57, 0x05, 0xa4, 0x56, 0x90, 0x64, 0x3d, 0x0e, 0x6e, 0x24, 0x43, 0x5e,
    0x54, 0x02, 0x99, 0x5b, 0xbe, 0x05, 0xab, 0xc9, 0xfb, 0xb7, 0x8f, 0x17, 0xcb, 0x59, 0xc0, 0x42,
    0x47, 0x79, 0xb1, 0xb8, 0x5c, 0x97, 0xef, 0xab, 0x65, 0x21, 0x88, 0xbd, 0x58, 0x3e, 0x9a, 0x8e,
    0x77, 0x84, 0x6c, 0x3d, 0x1a, 0x71, 0x7a, 0xb5, 0x9b, 0xc4, 0xde, 0xe5, 0x24, 0x18, 0x62, 0x61,
    0x58, 0x40, 0x14, 0x65, 0x6d, 0x8f, 0xa4, 0x82, 0x3e, 0xbe, 0xe9, 0x7a, 0xfa, 0x54, 0x9d, 0x9a,
    0xd3, 0x93, 0x44, 0x5c, 0x62, 0x9a, 0x26, 0x5e, 0x6b, 0x4c, 0xb5, 0x15, 0xe4, 0xe9, 0x4b, 0x4f,
    0x06, 0xd7, 0x59, 0x46, 0xfc, 0x4b, 0x3e, 0x09, 0x01, 0x0b, 0xd4, 0xa8, 0xcb, 0x39, 0x15, 0x4d,
    0x05, 0x0f, 0x3f, 0x08, 0x51, 0x8e, 0x3a, 0x20, 0x7e, 0xb3, 0x01, 0x7b, 0xe0, 0xeb, 0x3d, 0x62,
    0xdc, 0x0a, 0x9e, 0x63, 0x57, 0xcd, 0x68, 0xd8, 0xbe, 0xff, 0x3e, 0x3c, 0x33, 0x6c, 0x0d, 0xd8,
    0xb5, 0x4e, 0xdf, 0xeb, 0xef, 0x3b, 0x7d, 0xba, 0x32, 0xc0, 0x53, 0x48, 0x7e, 0x77, 0x91, 0xc7,
    0x7a, 0x2d, 0xb8, 0xaf, 0x8b, 0xe7, 0x8c, 0x0e, 0xa9, 0x39, 0x49, 0xdc, 0xa5, 0x4e, 0x7d, 0x3b,
    0xc9, 0xbf, 0x18, 0x41, 0x5e, 0xc0, 0x55, 0x4f, 0x90, 0x66, 0xfb, 0x19, 0xc8, 0x4b, 0x11, 0x93,
    0xff, 0x02, 0x03, 0x01, 0x00, 0x01
])

DEFAULT_RSA_PRIVATE_KEY_DER = bytearray([
    0x30, 0x82, 0x04, 0xbe, 0x02, 0x01, 0x00, 0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7,
    0x0d, 0x01, 0x01, 0x01, 0x05, 0x00, 0x04, 0x82, 0x04, 0xa8, 0x30, 0x82, 0x04, 0xa4, 0x02, 0x01,
    0x00, 0x02, 0x82, 0x01, 0x01, 0x00, 0xd4, 0x4f, 0xd9, 0xae, 0x7a, 0xd2, 0x87, 0x80, 0x67, 0x11,
    0x31, 0xb8, 0x5b, 0xac, 0x8b, 0x5f, 0xf2, 0x21, 0x28, 0x2c, 0x70, 0xec, 0x66, 0xe9, 0x18, 0xee,
    0x5e, 0xf1, 0xe3, 0xef, 0x09, 0xcb, 0x5e, 0xe0, 0xcd, 0xe4, 0x39, 0x6a, 0x3f, 0x43, 0x2a, 0x3e,
    0x1a, 0x06, 0xf2, 0xcc, 0xb0, 0x0f, 0x5b, 0xd8, 0xa1, 0x3f, 0x1c, 0xb8, 0xfa, 0x8c, 0xa4, 0xbf,
    0xa0, 0x57, 0x61, 0xcb, 0x35, 0xa9, 0x0f, 0x56, 0x76, 0x57, 0x05, 0xa4, 0x56, 0x90, 0x64, 0x3d,
    0x0e, 0x6e, 0x24, 0x43, 0x5e, 0x54, 0x02, 0x99, 0x5b, 0xbe, 0x05, 0xab, 0xc9, 0xfb, 0xb7, 0x8f,
    0x17, 0xcb, 0x59, 0xc0, 0x42, 0x47, 0x79, 0xb1, 0xb8, 0x5c, 0x97, 0xef, 0xab, 0x65, 0x21, 0x88,
    0xbd, 0x58, 0x3e, 0x9a, 0x8e, 0x77, 0x84, 0x6c, 0x3d, 0x1a, 0x71, 0x7a, 0xb5, 0x9b, 0xc4, 0xde,
    0xe5, 0x24, 0x18, 0x62, 0x61, 0x58, 0x40, 0x14, 0x65, 0x6d, 0x8f, 0xa4, 0x82, 0x3e, 0xbe, 0xe9,
    0x7a, 0xfa, 0x54, 0x9d, 0x9a, 0xd3, 0x93, 0x44, 0x5c, 0x62, 0x9a, 0x26, 0x5e, 0x6b, 0x4c, 0xb5,
    0x15, 0xe4, 0xe9, 0x4b, 0x4f, 0x06, 0xd7, 0x59, 0x46, 0xfc, 0x4b, 0x3e, 0x09, 0x01, 0x0b, 0xd4,
    0xa8, 0xcb, 0x39, 0x15, 0x4d, 0x05, 0x0f, 0x3f, 0x08, 0x51, 0x8e, 0x3a, 0x20, 0x7e, 0xb3, 0x01,
    0x7b, 0xe0, 0xeb, 0x3d, 0x62, 0xdc, 0x0a, 0x9e, 0x63, 0x57, 0xcd, 0x68, 0xd8, 0xbe, 0xff, 0x3e,
    0x3c, 0x33, 0x6c, 0x0d, 0xd8, 0xb5, 0x4e, 0xdf, 0xeb, 0xef, 0x3b, 0x7d, 0xba, 0x32, 0xc0, 0x53,
    0x48, 0x7e, 0x77, 0x91, 0xc7, 0x7a, 0x2d, 0xb8, 0xaf, 0x8b, 0xe7, 0x8c, 0x0e, 0xa9, 0x39, 0x49,
    0xdc, 0xa5, 0x4e, 0x7d, 0x3b, 0xc9, 0xbf, 0x18, 0x41, 0x5e, 0xc0, 0x55, 0x4f, 0x90, 0x66, 0xfb,
    0x19, 0xc8, 0x4b, 0x11, 0x93, 0xff, 0x02, 0x03, 0x01, 0x00, 0x01, 0x02, 0x82, 0x01, 0x00, 0x0f,
    0xa1, 0x85, 0x5c, 0x44, 0x2c, 0xa5, 0xcf, 0x3d, 0x47, 0x55, 0xca, 0xc5, 0xed, 0x11, 0x21, 0xd2,
    0x38, 0xc0, 0xb5, 0x6c, 0xe6, 0xea, 0xb8, 0xb4, 0x9e, 0x30, 0x1d, 0x4c, 0xf3, 0xb7, 0x5b, 0xe2,
    0xb3, 0x58, 0x55, 0x3a, 0x28, 0xe9, 0x59, 0x6f, 0x8d, 0xbc, 0xea, 0xd0, 0x0b, 0x63, 0xd6, 0xed,
    0xa3, 0x28, 0x53, 0xf6, 0x30, 0x64, 0x39, 0xe0, 0x93, 0x3f, 0x21, 0xcf, 0xd0, 0x5f, 0x36, 0x00,
    0x2c, 0x14, 0x70, 0x59, 0xb8, 0xfc, 0xaa, 0x8a, 0xc6, 0xb7, 0xfe, 0x41, 0xeb, 0x37, 0xd1, 0xa5,
    0x93, 0x56, 0xde, 0xc9, 0x9a, 0x19, 0x37, 0xd0, 0x0e, 0xd7, 0xe8, 0x9f, 0xc5, 0xf8, 0xdb, 0x3c,
    0x49, 0x6a, 0x52, 0x5e, 0xd9, 0x45, 0x5c, 0x1f, 0xb8, 0xea, 0x7f, 0xc9, 0xb4, 0x25, 0x53, 0x05,
    0x4b, 0xd6, 0xbf, 0xd0, 0xa5, 0x01, 0x23, 0xe3, 0xbd, 0xa9, 0x4f, 0x1c, 0x00, 0x7a, 0x3c, 0x1b,
    0xbb, 0xaa, 0x08, 0xd9, 0xd2, 0x8c, 0xdb, 0xb4, 0x6c, 0xff, 0x57, 0x64, 0x82, 0xbb, 0x02, 0x71,
    0x2d, 0x99, 0xea, 0x8a, 0x4e, 0x5a, 0xdb, 0x82, 0x20, 0x32, 0x51, 0xf8, 0x30, 0x98, 0x67, 0x4a,
    0x31, 0x73, 0xb1, 0xd7, 0x51, 0xc5, 0x71, 0x82, 0x2b, 0x99, 0xbc, 0x0c, 0xfa, 0x24, 0x4c, 0x0b,
    0x38, 0x73, 0xd8, 0xef, 0x6f, 0x5b, 0xda, 0x56, 0xc8, 0x6b, 0xcb, 0xf5, 0xc6, 0xaa, 0x4d, 0x8b,
    0x39, 0x0f, 0x0a, 0x43, 0x4e, 0x8b, 0x87, 0xe7, 0x98, 0x5a, 0x0d, 0x94, 0x55, 0xc7, 0x42, 0xb4,
    0x13, 0xfa, 0xed, 0x9c, 0xfe, 0xea, 0x2d, 0x95, 0xc1, 0xdc, 0x2f, 0x5d, 0x44, 0xf5, 0x2d, 0xab,
    0x8b, 0x79, 0x70, 0x0f, 0xe9, 0xa7, 0x17, 0xe8, 0x40, 0xd7, 0xa5, 0x0d, 0x97, 0xe9, 0x53, 0xa4,
    0xb4, 0x70, 0xbe, 0x19, 0x7b, 0x86, 0x2c, 0x26, 0xe7, 0xb1, 0x23, 0x22, 0x5a, 0xbd, 0x91, 0x02,
    0x81, 0x81, 0x00, 0xe2, 0x4d, 0x3c, 0xdc, 0x23, 0xb5, 0x2d, 0xc4, 0x66, 0xe7, 0xf2, 0xa4, 0x33,
    0xb9, 0xd6, 0xdd, 0x39, 0xc6, 0xee, 0x0e, 0xe6, 0x23, 0xbb, 0x9c, 0xf0, 0x6a, 0x10, 0xa8, 0x12,
    0xaa, 0x15, 0x8c, 0x08, 0x51, 0x5d, 0xed, 0x46, 0x33, 0xb0, 0x5d, 0x72, 0x02, 0xa0, 0x16, 0xb8,
    0xcf, 0xaa, 0x27, 0x09, 0x74, 0x97, 0x8c, 0xac, 0x8d, 0x4e, 0xbc, 0xe8, 0x62, 0xe5, 0x1e, 0x3c,
    0x74, 0xbb, 0xe9, 0xb9, 0xa6, 0x91, 0x02, 0x3f, 0x43, 0x4d, 0x2f, 0x01, 0x2a, 0x1c, 0xff, 0x4f,
    0x05, 0xf5, 0x98, 0x57, 0x3f, 0x67, 0xb0, 0x2d, 0x84, 0x2d, 0xd3, 0xf5, 0xb9, 0xd7, 0x37, 0x39,
    0x2a, 0x44, 0x04, 0x58, 0xa4, 0x17, 0x1e, 0x47, 0x38, 0x3f, 0x7d, 0x61, 0x97, 0xf2, 0xe4, 0xe5,
    0xeb, 0xe8, 0xbf, 0x55, 0xac, 0x6b, 0x74, 0xb8, 0x55, 0x2b, 0x1c, 0x12, 0x2a, 0x9c, 0x11, 0xf0,
    0x5b, 0x9d, 0xd7, 0x02, 0x81, 0x81, 0x00, 0xf0, 0x2c, 0x9d, 0xa3, 0x34, 0x0b, 0x6a, 0x01, 0x69,
    0x6c, 0xaa, 0xbf, 0xee, 0x95, 0xcc, 0x12, 0x24, 0x37, 0xeb, 0xda, 0x30, 0xdb, 0xe5, 0x4b, 0x34,
    0x5b, 0x56, 0x9e, 0x46, 0xeb, 0xe5, 0xb5, 0x75, 0x45, 0xac, 0xb7, 0xa2, 0x52, 0x69, 0x04, 0xd2,
    0x5f, 0x98, 0x59, 0x4f, 0xb6, 0xf3, 0x8e, 0x9f, 0x34, 0x8d, 0x07, 0x22, 0x7e, 0xc0, 0x28, 0x79,
    0xe1, 0x25, 0x0a, 0x03, 0x96, 0xb8, 0xa8, 0x0f, 0xc8, 0x37, 0x2d, 0xb0, 0xe8, 0xc0, 0x1e, 0x3b,
    0x4a, 0xf2, 0xcc, 0x6b, 0x60, 0x83, 0x88, 0x2d, 0x71, 0x8f, 0x91, 0xab, 0x1a, 0x02, 0x8e, 0x03,
    0xfb, 0xc2, 0x9a, 0x4e, 0x91, 0xd4, 0x49, 0x2c, 0x4c, 0x69, 0x8c, 0xe9, 0x4b, 0xbe, 0x88, 0xe2,
    0xd9, 0xa8, 0x7f, 0x3d, 0xe9, 0x67, 0x39, 0xd7, 0xd4, 0x11, 0xa0, 0xb1, 0xcd, 0x8b, 0x59, 0x5f,
    0xce, 0x35, 0x16, 0x26, 0x30, 0xe6, 0x19, 0x02, 0x81, 0x81, 0x00, 0x9b, 0x59, 0x44, 0x47, 0x26,
    0xa8, 0x10, 0x63, 0xfb, 0xf4, 0x8c, 0x27, 0xd6, 0x6e, 0x63, 0xa6, 0x78, 0x2c, 0x2c, 0x6d, 0xc3,
    0xe4, 0x91, 0xbd, 0x39, 0x78, 0xc6, 0x38, 0x6a, 0x9f, 0xa1, 0xad, 0x00, 0x64, 0xc2, 0xe2, 0xc8,
    0x47, 0x61, 0x71, 0xb4, 0x7b, 0x42, 0xe4, 0x76, 0x37, 0xf0, 0x69, 0x5d, 0xdf, 0x50, 0xcd, 0xbc,
    0x02, 0x41, 0x24, 0x03, 0x2f, 0x28, 0x73, 0xaa, 0x32, 0xc4, 0x70, 0xbd, 0x06, 0x30, 0x13, 0x67,
    0xd4, 0x4e, 0x9e, 0xce, 0xe0, 0xd7, 0x09, 0x18, 0x79, 0x51, 0xd0, 0x23, 0x4c, 0x9e, 0x64, 0x5d,
    0xca, 0x98, 0x1f, 0x22, 0x57, 0x51, 0xfb, 0x51, 0xdd, 0xc6, 0xd5, 0x68, 0xf8, 0x33, 0xfa, 0x90,
    0x0f, 0x77, 0xde, 0x1d, 0x69, 0xce, 0xce, 0xfd, 0x5b, 0x05, 0xea, 0x9a, 0xe8, 0x82, 0xd7, 0x9c,
    0x56, 0xb3, 0x02, 0x51, 0x22, 0x39, 0x03, 0x43, 0x89, 0xd0, 0xff, 0x02, 0x81, 0x80, 0x13, 0x1c,
    0x89, 0xc2, 0xb5, 0xde, 0x7e, 0xa5, 0xf4, 0x1c, 0xa8, 0x8d, 0xb3, 0x4f, 0x8a, 0x38, 0x9b, 0x57,
    0x33, 0xd6, 0x5d, 0xf2, 0xf1, 0x91, 0x05, 0x6e, 0x8b, 0x3a, 0xf7, 0x0b, 0xc8, 0x70, 0xa3, 0x0f,
    0x53, 0x4a, 0x1d, 0x89, 0x8f, 0x3f, 0xc9, 0xf9, 0xbf, 0x66, 0xc3, 0xf8, 0x1b, 0xf3, 0x6a, 0x69,
    0xc5, 0x1b, 0x1f, 0x3c, 0x94, 0xcf, 0xe3, 0xba, 0xed, 0xb6, 0x99, 0x48, 0x82, 0x13, 0x25, 0x86,
    0x5a, 0x15, 0xb1, 0xb1, 0x23, 0xb0, 0x84, 0x29, 0x57, 0x9e, 0xba, 0xa0, 0xa8, 0x76, 0xca, 0x9e,
    0xf1, 0xbc, 0xb6, 0xaf, 0xd0, 0x2a, 0x3a, 0xd8, 0xea, 0xc8, 0x5a, 0x9e, 0x32, 0x15, 0x4c, 0x88,
    0x1c, 0x12, 0x11, 0x72, 0x6c, 0x8b, 0xf9, 0xf9, 0x35, 0xf6, 0x42, 0x17, 0xf3, 0x95, 0xdf, 0xbd,
    0xc9, 0x55, 0x4f, 0x30, 0xba, 0xf8, 0xf6, 0xad, 0xb2, 0xfd, 0xbb, 0x36, 0x42, 0xe9, 0x02, 0x81,
    0x81, 0x00, 0xad, 0xf0, 0xc0, 0xfc, 0x55, 0x47, 0x8a, 0x03, 0x2b, 0x5c, 0x1c, 0x6e, 0xef, 0xf6,
    0x96, 0x68, 0xee, 0xa8, 0xd0, 0x6d, 0x70, 0x4f, 0x7f, 0x3e, 0x17, 0x2b, 0xfd, 0x7e, 0x22, 0x8c,
    0xea, 0x25, 0xe3, 0xbb, 0xa4, 0xa1, 0x57, 0xe7, 0x3e, 0xc0, 0x47, 0xf8, 0x7b, 0xa6, 0xd2, 0x48,
    0x68, 0xc0, 0x8a, 0xe0, 0xb2, 0x6b, 0x5d, 0xf9, 0x32, 0x6e, 0x70, 0x5a, 0xb9, 0x77, 0xd9, 0xbf,
    0x6d, 0xea, 0x53, 0xe2, 0x4f, 0xa8, 0x4c, 0x1c, 0xfa, 0x69, 0x49, 0x26, 0x48, 0x8a, 0xc5, 0x92,
    0x77, 0x6b, 0x7a, 0x89, 0xc3, 0xef, 0x6d, 0x1c, 0x44, 0x10, 0xe6, 0xaf, 0x47, 0x18, 0x9f, 0x99,
    0x09, 0xb4, 0x3b, 0x63, 0xf7, 0xbf, 0xe4, 0xe7, 0xe5, 0x98, 0xe2, 0x57, 0x85, 0xbb, 0x78, 0xb5,
    0xd1, 0xc3, 0x64, 0x8d, 0x4d, 0x4f, 0x02, 0xdb, 0x2c, 0x51, 0x58, 0xa3, 0xc7, 0x35, 0xf1, 0x2d,
    0x7a, 0x0a
])

# This matches FIXTURE_USER_D_KEY in test_nac_consumer.
FIXTURE_USER_E_KEY = bytearray([
    0x30, 0x82, 0x01, 0x22, 0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01,
    0x01, 0x05, 0x00, 0x03, 0x82, 0x01, 0x0f, 0x00, 0x30, 0x82, 0x01, 0x0a, 0x02, 0x82, 0x01, 0x01,
    0x00, 0xd2, 0x1c, 0x8d, 0x80, 0x78, 0xcc, 0x92, 0xb7, 0x6e, 0xfd, 0x28, 0xdc, 0xb4, 0xa7, 0x81,
    0x98, 0xa4, 0x31, 0x02, 0x01, 0x49, 0x58, 0xc4, 0x27, 0x0e, 0x7d, 0xe2, 0xa4, 0xca, 0xd0, 0x98,
    0x2a, 0xb6, 0x0d, 0xff, 0x14, 0x36, 0xbf, 0x3e, 0xb9, 0xa1, 0x9c, 0x8b, 0x5b, 0xd8, 0x47, 0x12,
    0x3e, 0xfe, 0x66, 0xb7, 0x73, 0x5f, 0x54, 0xc3, 0xe7, 0x3d, 0x03, 0xe5, 0xab, 0x56, 0x3f, 0xbf,
    0x25, 0xa6, 0xe6, 0x9b, 0x74, 0x83, 0xab, 0x30, 0xba, 0xab, 0xff, 0x20, 0xb6, 0xb7, 0xee, 0x4f,
    0x77, 0x9e, 0xc3, 0xfe, 0xb8, 0xef, 0x2a, 0x15, 0x2d, 0x24, 0x68, 0x49, 0x58, 0xe5, 0x3b, 0x50,
    0xbb, 0x4e, 0x72, 0x92, 0xbb, 0xfc, 0x98, 0x62, 0xe2, 0x58, 0xc7, 0x2d, 0xf6, 0x46, 0xb1, 0x07,
    0xbc, 0x68, 0x68, 0x29, 0xf6, 0x31, 0x79, 0x9c, 0xc6, 0x00, 0xc3, 0x5d, 0xce, 0x4a, 0xcf, 0x26,
    0xfb, 0xf6, 0x9b, 0x3b, 0x7a, 0xa6, 0xfa, 0x89, 0xaa, 0xc9, 0xc0, 0xf2, 0x08, 0x46, 0xcd, 0x45,
    0xf6, 0x38, 0xab, 0x90, 0x1e, 0xd6, 0xa1, 0x6e, 0x48, 0xa0, 0xe5, 0x5f, 0x59, 0x35, 0x2c, 0x0d,
    0xe9, 0x3d, 0x3c, 0x9f, 0x8d, 0x28, 0xec, 0x24, 0xbc, 0x63, 0x43, 0x75, 0x00, 0x07, 0xf3, 0x45,
    0xf4, 0x93, 0x35, 0x42, 0x4c, 0x90, 0xea, 0x4f, 0x0a, 0x44, 0x4e, 0xda, 0x7a, 0xd5, 0xad, 0x8d,
    0x12, 0x21, 0xc5, 0x63, 0x74, 0xc2, 0x80, 0x2f, 0xe6, 0x27, 0x54, 0xc3, 0xf8, 0xd6, 0x24, 0x7e,
    0x44, 0x95, 0xc8, 0x3e, 0x1f, 0x43, 0x8e, 0x56, 0x67, 0xbd, 0xb5, 0x9d, 0xfd, 0x9a, 0xad, 0x5a,
    0x0a, 0x88, 0xc3, 0x8c, 0xb9, 0xaf, 0x29, 0x71, 0x51, 0x70, 0x87, 0x6f, 0xee, 0x0e, 0xd0, 0x27,
    0x3b, 0x95, 0xeb, 0x66, 0xe1, 0x4a, 0x4b, 0x67, 0xab, 0x90, 0x43, 0xd5, 0x51, 0xad, 0x57, 0x08,
    0xd5, 0x02, 0x03, 0x01, 0x00, 0x01
])

def dump(*list):
    result = ""
    for element in list:
        result += (element if type(element) is str else str(element)) + " "
    print(result)

def createKeyChain():
    """
    Create an in-memory KeyChain with default keys.

    :return: A tuple with the new KeyChain and certificate name.
    :rtype: (KeyChain,Name)
    """
    identityStorage = MemoryIdentityStorage()
    privateKeyStorage = MemoryPrivateKeyStorage()
    keyChain = KeyChain(
      IdentityManager(identityStorage, privateKeyStorage),
      NoVerifyPolicyManager())

    # Initialize the storage.
    keyName = Name("/testname/DSK-123")
    certificateName = keyName.getSubName(0, keyName.size() - 1).append(
      "KEY").append(keyName.get(-1)).append("ID-CERT").append("0")
    identityStorage.addKey(
      keyName, KeyType.RSA, Blob(DEFAULT_RSA_PUBLIC_KEY_DER, False))
    privateKeyStorage.setKeyPairForKeyName(
      keyName, KeyType.RSA, DEFAULT_RSA_PUBLIC_KEY_DER,
      DEFAULT_RSA_PRIVATE_KEY_DER)

    return keyChain, certificateName

class TestProducer(object):
    """
    Create a TestProducer with an OnInterestCallback for use with
    registerPrefix to answer interests with prepared packets. When finished,
    a callback will set _enabled to False.
    """
    def __init__(self, contentName, userKeyName, keyChain, certificateName):
        self._enabled = True
        self._responseCount = 0

        # Imitate test_consumer from the PyNDN integration tests.
        cKeyName = Name("/Prefix/SAMPLE/Content/C-KEY/1")
        dKeyName = Name("/Prefix/READ/D-KEY/1/2")

        # Generate the E-KEY and D-KEY.
        params = RsaKeyParams()
        fixtureDKeyBlob = RsaAlgorithm.generateKey(params).getKeyBits()
        fixtureEKeyBlob = RsaAlgorithm.deriveEncryptKey(
          fixtureDKeyBlob).getKeyBits()

        # The user key.
        fixtureUserEKeyBlob = Blob(FIXTURE_USER_E_KEY)

        # Load the C-KEY.
        fixtureCKeyBlob = Blob(AES_KEY, False)

        # Imitate createEncryptedContent.
        self._contentData = Data(contentName)
        encryptParams = EncryptParams(EncryptAlgorithmType.AesCbc)
        encryptParams.setInitialVector(Blob(INITIAL_VECTOR, False))
        Encryptor.encryptData(
          self._contentData, Blob(DATA_CONTENT, False), cKeyName,
          fixtureCKeyBlob,  encryptParams)
        keyChain.sign(self._contentData, certificateName)

        # Imitate createEncryptedCKey.
        self._cKeyData = Data(cKeyName)
        encryptParams = EncryptParams(EncryptAlgorithmType.RsaOaep)
        Encryptor.encryptData(
          self._cKeyData, fixtureCKeyBlob, dKeyName, fixtureEKeyBlob,
          encryptParams)
        keyChain.sign(self._cKeyData, certificateName)

        # Imitate createEncryptedDKey.
        self._dKeyData = Data(dKeyName)
        encryptParams = EncryptParams(EncryptAlgorithmType.RsaOaep)
        Encryptor.encryptData(
          self._dKeyData, fixtureDKeyBlob, userKeyName, fixtureUserEKeyBlob,
          encryptParams)
        keyChain.sign(self._dKeyData, certificateName)

    def onInterest(self, prefix, interest, face, interestFilterId, filter):
        if interest.matchesName(self._contentData.getName()):
            data = self._contentData
        elif interest.matchesName(self._cKeyData.getName()):
            data = self._cKeyData
        elif interest.matchesName(self._dKeyData.getName()):
            data = self._dKeyData
        else:
            return

        dump("Sending Data packet " + data.getName().toUri())
        face.putData(data)

        self._responseCount += 1
        if self._responseCount >= 3:
            # We sent all the packets.
            self._enabled = False

    def onRegisterFailed(self, prefix):
        dump("Register failed for prefix", prefix.toUri())
        self._enabled = False

def main():
    # The default Face will connect using a Unix socket, or to "localhost".
    face = Face()

    (keyChain, certificateName) = createKeyChain()
    face.setCommandSigningInfo(keyChain, certificateName)

    userKeyName = Name("/U/Key")
    contentPrefix = Name("/Prefix/SAMPLE")
    contentName = Name(contentPrefix).append("Content")

    testProducer = TestProducer(
      contentName, userKeyName, keyChain, certificateName)

    prefix = Name("/Prefix")
    dump("Register prefix", prefix.toUri())
    face.registerPrefix(
      prefix, testProducer.onInterest, testProducer.onRegisterFailed)

    while testProducer._enabled:
        face.processEvents()
        # We need to sleep for a few milliseconds so we don't use 100% of the CPU.
        time.sleep(0.01)

main()
