# -*- coding: utf-8 -*-

# Copyright: (c) 2022, Cindy Zhao (@cizhao) <cizhao@cisco.com>
# Simplified BSD License (see licenses/simplified_bsd.txt or https://opensource.org/licenses/BSD-2-Clause)

from __future__ import (absolute_import, division, print_function)
from flask import request

from matplotlib.font_manager import json_dump, json_load
__metaclass__ = type

from copy import deepcopy
import re
import os
import ast
import datetime
import shutil
import tempfile
import time
from xml.dom import minidom
from jsonpath_ng import parse
from ansible.module_utils.basic import json
from ansible.module_utils.basic import env_fallback
from ansible.module_utils.six import PY3
from ansible.module_utils.six.moves import filterfalse
from ansible.module_utils.six.moves.urllib.parse import urlencode, urljoin
from ansible.module_utils.urls import fetch_url
from ansible.module_utils._text import to_native, to_text
from ansible.module_utils.connection import Connection
import requests
try:
    from requests_toolbelt.multipart.encoder import MultipartEncoder
    HAS_MULTIPART_ENCODER = True
except ImportError:
    HAS_MULTIPART_ENCODER = False


if PY3:
    def cmp(a, b):
        return (a > b) - (a < b)