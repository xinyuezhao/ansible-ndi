# -*- coding: utf-8 -*-

# Copyright: (c) 2022, Cindy Zhao (@cizhao) <cizhao@cisco.com>
# Simplified BSD License (see licenses/simplified_bsd.txt or https://opensource.org/licenses/BSD-2-Clause)

from __future__ import absolute_import, division, print_function
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
    required: yes
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
    state: query
  delegate_to: localhost
  register: query_result
'''

RETURN = r'''
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.cisco.ndi.plugins.module_utils.ndi import NDIModule, ndi_argument_spec

def main():
    argument_spec = ndi_argument_spec()
    argument_spec.update(
        ig_name=dict(type='str'),
        name=dict(type='str'),
        description=dict(type='str'),
        site_name=dict(type='str'),
        file=dict(type='str'),
        manual=dict(type='str'),
        state=dict(type='str', default='query', choices=['query']),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        required_if=[['state', 'absent', ['name']],
                     ['state', 'present', ['name']]]
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
    site = ndi.get_site_id(path, site_name)

    # get latest pre-change analysis
    pcv_path = '{0}/{1}/prechangeAnalysis'.format(path, ig_name)
    epoch_delta_job_id = ndi.get_epoch_job_id(pcv_path, sort="-analysisSubmissionTime", fabricId=site)
    pcv_result_path = 'epochDelta/insightsGroup/{0}/fabric/{1}/job/{2}/health/view/eventSeverity'.format(ig_name, site_name, epoch_delta_job_id)
    ndi.existing = ndi.get_pre_change_result(pcv_result_path)

    # if state == 'present' and file:

        # epoch_path = 'events/insightsGroup/{0}/fabric/{1}/epochs'.format(ig_name, site_name)
        # status=FINISHED&$sort=-collectionTime%2C-analysisStartTime&$page=0&$size=1&$epochType=ONLINE%2C+OFFLINE
        # epoch = ndi.get_epochs(path)


if __name__ == "__main__":
    main()
