# -*- coding: utf-8 -*-

# Copyright: (c) 2022, Cindy Zhao (@cizhao) <cizhao@cisco.com>
# Simplified BSD License (see licenses/simplified_bsd.txt or https://opensource.org/licenses/BSD-2-Clause)

from __future__ import absolute_import, division, print_function
import json
import os
import time
__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = r'''
---
module: ndi_pcv
version_added: "0.0.1"
short_description: Manage pre-change validation
description:
- Manage pre-change validation on Cisco Nexus Dashboard Insights (NDI).
author:
- Cindy Zhao (@cizhao)
options:
  ig_name:
    description:
    - The name of the insights group.
    type: str
    required: yes
    aliases: [ fab_name ]
  name:
    description:
    - The name of the pre-change validation.
    type: str
  description:
    description:
    - Description for the pre-change validation.
    type: str
    aliases: [ descr ]
  site_name:
    description:
    - Name of the Assurance Entity.
    type: str
    aliases: [ site ]
  file:
    description:
    - Optional parameter if creating new pre-change analysis from file.
    type: str
  manual:
    description:
    - Optional parameter if creating new pre-change analysis from change-list (manual)
    type: str
  state:
    description:
    - Use C(query) for retrieving the version object.
    type: str
    choices: [ query ]
    default: query
extends_documentation_fragment: cisco.ndi.modules
'''

EXAMPLES = r'''
- name: Get prechange validation result
  cisco.ndi.ndi_pcv:
    ig_name: exampleIG
    state: query
  delegate_to: localhost
  register: query_results

- name: Get a specific prechange validation result
  cisco.ndi.ndi_pcv:
    ig_name: exampleIG
    site_name: siteName
    name: demoName
    state: query
  delegate_to: localhost
  register: query_result

- name: Create a new Pre-Change analysis from file
  cisco.ndi.ndi_pcv:
    ig_name: igName
    site_name: siteName
    name: demoName
    file: configFilePath
    state: present
  delegate_to: localhost
  register: present_pcv

- name: Present Pre-Change analysis from manual changes
  cisco.ndi.ndi_pcv:
    ig_name: idName
    site_name: SiteName
    name: demoName
    manual: |
        [
            {
              "fvTenant": {
                "attributes": {
                  "name": "AnsibleTest",
                  "dn": "uni/tn-AnsibleTest",
                  "status": "deleted"
                }
              }
            }
        ]
    state: present
  delegate_to: localhost
  register: present_pcv_manual

- name: Delete Pre-Change analysis
  cisco.ndi.ndi_pcv:
    ig_name: igName
    site_name: siteName
    name: demoName
    state: absent
  delegate_to: localhost
  register: rm_pcv
'''

RETURN = r'''
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.cisco.ndi.plugins.module_utils.ndi import NDIModule, ndi_argument_spec

def main():
    argument_spec = ndi_argument_spec()
    argument_spec.update(
        ig_name=dict(type='str', required=True),
        name=dict(type='str'),
        description=dict(type='str'),
        site_name=dict(type='str'),
        file=dict(type='str'),
        manual=dict(type='str'),
        state=dict(type='str', default='query', choices=['query', 'absent', 'present']),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        required_if=[['state', 'absent', ['name'], ['site_name']],
                     ['state', 'present', ['name'], ['site_name']]]
    )

    ndi = NDIModule(module)

    state = ndi.params.get("state")
    name = ndi.params.get("name")
    site_name = ndi.params.get('site_name')
    ig_name = ndi.params.get('ig_name')
    description = ndi.params.get('description')
    file = ndi.params.get('file')
    manual = ndi.params.get('manual')

    path = 'config/insightsGroup'
    pcvs_path = '{0}/{1}/prechangeAnalysis?$sort=-analysisSubmissionTime'.format(path, ig_name)
    pcv_results = ndi.get_pcv_results(pcvs_path)
    ndi.existing = pcv_results
    if name is not None and site_name is not None:
        site_id = ndi.get_site_id(path, site_name)
        pcv_path = '{0}/{1}/fabric/{2}/prechangeAnalysis'.format(path, ig_name, site_name)
        ndi.existing = ndi.get_pre_change_result(pcv_results, name, site_id, pcv_path)

    if state == 'query':
        pass

    elif state == 'absent':
        ndi.previous = ndi.existing
        job_id = ndi.existing.get('jobId')
        if ndi.existing and job_id:
            if module.check_mode:
                ndi.existing = {}
            else:
                rm_path = '{0}/{1}/prechangeAnalysis/jobs'.format(path, ig_name)
                rm_payload = [job_id]
                ndi.existing = ndi.request(rm_path, method='POST', data=rm_payload)

    elif state == 'present':
        ndi.previous = ndi.existing
        if ndi.existing:
            ndi.exit_json()
        epoch_path = 'events/insightsGroup/{0}/fabric/{1}/epochs?$size=1&$status=FINISHED'.format(ig_name, site_name)
        base_epoch_data = ndi.get_epochs(epoch_path)

        data = {
            "allowUnsupportedObjectModification": "true",
            "analysisSubmissionTime": round(time.time() * 1000),
            "baseEpochId": base_epoch_data["epochId"],
            "baseEpochCollectionTimestamp": base_epoch_data["collectionTimeMsecs"],
            "fabricUuid": base_epoch_data["fabricId"],
            "description": description,
            "name": name,
            "assuranceEntityName": site_name,
        }
        if file:
            if not os.path.exists(file):
                ndi.fail_json(msg="File not found : {0}".format(file))

            create_pcv_path = '{0}/{1}/fabric/{2}/prechangeAnalysis/fileChanges'.format(path, ig_name, site_name)
            ndi.existing = ndi.request(create_pcv_path, method='POST', file=file, data=data)
        if manual:
            data["imdata"] = json.loads(manual)
            create_pcv_path = '{0}/{1}/fabric/{2}/prechangeAnalysis/manualChanges?action=RUN'.format(path, ig_name, site_name)
            ndi.existing = ndi.request(create_pcv_path, method='POST', data=data)
    ndi.exit_json()
if __name__ == "__main__":
    main()
