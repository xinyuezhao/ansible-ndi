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

def ndi_argument_spec():
    return dict()

def update_qs(params):
    ''' Append key-value pairs to self.filter_string '''
    accepted_params = dict((k, v) for (k, v) in params.items() if v is not None)
    return '?' + urlencode(accepted_params)

class NDIModule(object):

    def __init__(self, module):
        self.module = module
        self.params = module.params
        self.result = dict(changed=False)
        self.headers = {'Content-Type': 'text/json'}

        # normal output
        self.existing = dict()

        # ndi_rest output
        self.jsondata = None
        self.error = dict(code=None, message=None, info=None)

        # info output
        self.previous = dict()
        self.proposed = dict()
        self.sent = dict()
        self.stdout = None

        # debug output
        self.has_modified = False
        self.filter_string = ''
        self.method = None
        self.path = None
        self.response = None
        self.status = None
        self.url = None

        if self.module._debug:
            self.module.warn('Enable debug output because ANSIBLE_DEBUG was set.')
            self.params['output_level'] = 'debug'

        self.connection = Connection(self.module._socket_path)
        if self.connection.get_platform() == "cisco.nd":
            self.platform = "nd"

    def exit_json(self, **kwargs):
        ''' Custom written method to exit from module. '''

        if self.params.get('state') in ('absent', 'present', 'upload', 'restore', 'download', 'move', 'clone'):
            if self.params.get('output_level') in ('debug', 'info'):
                self.result['previous'] = self.previous
            # FIXME: Modified header only works for PATCH
            if not self.has_modified and self.previous != self.existing:
                self.result['changed'] = True
        if self.stdout:
            self.result['stdout'] = self.stdout

        # Return the gory details when we need it
        if self.params.get('output_level') == 'debug':
            self.result['method'] = self.method
            self.result['response'] = self.response
            self.result['status'] = self.status
            self.result['url'] = self.url
            self.result['socket'] = self.module._socket_path

            if self.params.get('state') in ('absent', 'present'):
                self.result['sent'] = self.sent
                self.result['proposed'] = self.proposed

        self.result['current'] = self.existing

        if self.module._diff and self.result.get('changed') is True:
            self.result['diff'] = dict(
                before=self.previous,
                after=self.existing,
            )

        self.result.update(**kwargs)
        self.module.exit_json(**self.result)

    def fail_json(self, msg, **kwargs):
        ''' Custom written method to return info on failure. '''

        if self.params.get('state') in ('absent', 'present'):
            if self.params.get('output_level') in ('debug', 'info'):
                self.result['previous'] = self.previous
            # FIXME: Modified header only works for PATCH
            if not self.has_modified and self.previous != self.existing:
                self.result['changed'] = True
        if self.stdout:
            self.result['stdout'] = self.stdout

        # Return the gory details when we need it
        if self.params.get('output_level') == 'debug':
            if self.url is not None:
                self.result['method'] = self.method
                self.result['response'] = self.response
                self.result['status'] = self.status
                self.result['url'] = self.url
                self.result['socket'] = self.module._socket_path

            if self.params.get('state') in ('absent', 'present'):
                self.result['sent'] = self.sent
                self.result['proposed'] = self.proposed

        self.result['current'] = self.existing

        self.result.update(**kwargs)
        self.module.fail_json(msg=msg, **self.result)

    def request(self, path, method=None, data=None, qs=None, api_version="v2"):
        ''' Generic HTTP method for NDI requests. '''
        self.path = path

        if method is not None:
            self.method = method

        # If we PATCH with empty operations, return
        if method == 'PATCH' and not data:
            return {}

        # if method in ['PATCH', 'PUT']:
        #     if qs is not None:
        #         qs['enableVersionCheck'] = 'true'
        #     else:
        #         qs = dict(enableVersionCheck='true')

        if method in ['PATCH']:
            if qs is not None:
                qs['validate'] = 'false'
            else:
                qs = dict(validate='false')

        resp = None
        self.connection.set_params(self.params)
        if api_version is not None:
            uri = '/sedgeapi/v1/cisco-nir/api/api/telemetry/{0}/{1}'.format(api_version, self.path)
            # uri = '/mso/api/{0}/{1}'.format(api_version, self.path)
        else:
            uri = self.path

        if qs is not None:
            uri = uri + update_qs(qs)

        try:
            info = self.connection.send_request(method, uri, json.dumps(data))
            self.url = info.get('url')
            info.pop('date')
        except Exception as e:
            try:
                error_obj = json.loads(to_text(e))
            except Exception:
                error_obj = dict(error=dict(
                    code=-1,
                    message="Unable to parse error output as JSON. Raw error message: {0}".format(e),
                    exception=to_text(e)
                ))
                pass
            self.fail_json(msg=error_obj['error']['message'])

        self.response = info.get('msg')
        self.status = info.get('status', -1)

        # Get change status from HTTP headers
        if 'modified' in info:
            self.has_modified = True
            if info.get('modified') == 'false':
                self.result['changed'] = False
            elif info.get('modified') == 'true':
                self.result['changed'] = True

        # 200: OK, 201: Created, 202: Accepted
        if self.status in (200, 201, 202):
            try:
                output = resp.read()
                if output:
                    try:
                        return json.loads(output)
                    except Exception as e:
                        self.error = dict(code=-1, message="Unable to parse output as JSON, see 'raw' output. {0}".format(e))
                        self.result['raw'] = output
                        return
            except AttributeError:
                return info.get('body')

        # 204: No Content
        elif self.status == 204:
            return {}

        # 404: Not Found
        elif self.method == 'DELETE' and self.status == 404:
            return {}

        # 400: Bad Request, 401: Unauthorized, 403: Forbidden,
        # 405: Method Not Allowed, 406: Not Acceptable
        # 500: Internal Server Error, 501: Not Implemented
        elif self.status >= 400:
            self.result['status'] = self.status
            body = info.get('body')
            if body is not None:
                try:
                    if isinstance(body, dict):
                        payload = body
                    else:
                        payload = json.loads(body)
                except Exception as e:
                    self.error = dict(code=-1, message="Unable to parse output as JSON, see 'raw' output. %s" % e)
                    self.result['raw'] = body
                    self.fail_json(msg='NDI Error:', data=data, info=info)
                self.error = payload
                if 'code' in payload:
                    self.fail_json(msg='NDI Error {code}: {message}'.format(**payload), data=data, info=info, payload=payload)
                else:
                    self.fail_json(msg='NDI Error:'.format(**payload), data=data, info=info, payload=payload)
            else:
                # Connection error
                msg = 'Connection failed for {0}. {1}'.format(info.get('url'), info.get('msg'))
                self.error = msg
                self.fail_json(msg=msg)
            return {}

    # def get_site(self, ig_name, site_name):
    # uri = "/sedgeapi/v1/cisco-nir/api/api/telemetry/v2/config/insightsGroup?insightsGroupName={0}".format(ig_name)
    # obj = self.connection.send_request("GET", uri,)
    # if obj['status'] != 200:
    #     self.module.fail_json(
    #         msg=obj,
    #         **self.result)
    # for site in obj['body']['value']['data'][0]['assuranceEntities']:
    #     if site['name'] == site_name:
    #         return site

    def query_obj(self, path, qs=False, **kwargs):
        ''' Query the NDI REST API for the whole object at a path '''
        if qs:
            obj = self.request(path, method='GET', qs=kwargs)
        else:
            obj = self.request(path, method='GET')
        if obj == {}:
            return {}
        for kw_key, kw_value in kwargs.items():
            if kw_value is None:
                continue
            if obj.get(kw_key) != kw_value:
                return {}
        return obj

    # def query_objs(self, path, key=None, **kwargs):
    #     ''' Query the ND REST API for objects in a path '''
    #     found = []
    #     objs = self.request(path, method='GET')

    #     if objs == {}:
    #         return found

    #     if key is None:
    #         key = path

    #     if key not in objs:
    #         self.fail_json(msg="Key '{0}' missing from data".format(objs))

    #     for obj in objs.get(key):
    #         for kw_key, kw_value in kwargs.items():
    #             if kw_value is None:
    #                 continue
    #             if obj.get(kw_key) != kw_value:
    #                 break
    #         else:
    #             found.append(obj)
    #     return found

    # def get_obj(self, path, **kwargs):
    #     ''' Get a specific object from a set of ND REST objects '''
    #     objs = self.query_objs(path, **kwargs)
    #     if len(objs) == 0:
    #         return {}
    #     if len(objs) > 1:
    #         self.fail_json(msg='More than one object matches unique filter: {0}'.format(kwargs))
    #     return objs[0]

    def get_site_id(self, path, site_name):
        obj = self.query_obj(path)
        for site in obj['value']['data'][0]['assuranceEntities']:
            if site['name'] == site_name:
                return site['uuid']

    def get_pcv_results(self, path, **kwargs):
        obj = self.query_obj(path, qs=True, **kwargs)
        return obj['value']['data']

    def get_pre_change_result(self, pcv_results, name, site_id, path):
        for pcv in pcv_results:
            if pcv.get("name") == name and pcv.get("fabricUuid") == site_id:
                pcv_job_id = pcv.get("jobId")
                pcv_path = '{0}/{1}'.format(path, pcv_job_id)
                obj = self.query_obj(pcv_path)
        return obj['value']['date']

    def get_epochs(self, path, **kwargs):
        obj = self.query_obj(path, qs=True, **kwargs)
        return obj['value']['data'][0]


