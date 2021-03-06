# Copyright 2012 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import datetime

from lxml import etree
from webob import exc

from nova.api.openstack.compute.contrib import flavor_access
from nova.api.openstack.compute import flavors
from nova.compute import instance_types
from nova import context
from nova import exception
from nova import test
from nova.tests.api.openstack import fakes


def generate_instance_type(flavorid, ispublic):
    return {
        'id': flavorid,
        'flavorid': str(flavorid),
        'root_gb': 1,
        'ephemeral_gb': 1,
        'name': u'test',
        'deleted': False,
        'created_at': datetime.datetime(2012, 1, 1, 1, 1, 1, 1),
        'updated_at': None,
        'memory_mb': 512,
        'vcpus': 1,
        'swap': 512,
        'rxtx_factor': 1.0,
        'extra_specs': {},
        'deleted_at': None,
        'vcpu_weight': None,
        'is_public': bool(ispublic)
    }


INSTANCE_TYPES = {
        '0': generate_instance_type(0, True),
        '1': generate_instance_type(1, True),
        '2': generate_instance_type(2, False),
        '3': generate_instance_type(3, False)}


ACCESS_LIST = [{'flavor_id': '2', 'project_id': 'proj2'},
               {'flavor_id': '2', 'project_id': 'proj3'},
               {'flavor_id': '3', 'project_id': 'proj3'}]


def fake_get_instance_type_access_by_flavor_id(flavorid):
    res = []
    for access in ACCESS_LIST:
        if access['flavor_id'] == flavorid:
            res.append(access)
    return res


def fake_get_instance_type_by_flavor_id(flavorid):
    return INSTANCE_TYPES[flavorid]


def _has_flavor_access(flavorid, projectid):
    for access in ACCESS_LIST:
        if access['flavor_id'] == flavorid and \
           access['project_id'] == projectid:
                return True
    return False


def fake_get_all_types(context, inactive=0, filters=None):
    if filters == None or filters['is_public'] == None:
        return INSTANCE_TYPES

    res = {}
    for k, v in INSTANCE_TYPES.iteritems():
        if filters['is_public'] and _has_flavor_access(k, context.project_id):
            res.update({k: v})
            continue
        if v['is_public'] == filters['is_public']:
            res.update({k: v})

    return res


class FakeRequest(object):
    environ = {"nova.context": context.get_admin_context()}


class FlavorAccessTest(test.TestCase):
    def setUp(self):
        super(FlavorAccessTest, self).setUp()
        self.flavor_controller = flavors.Controller()
        self.flavor_access_controller = flavor_access.FlavorAccessController()
        self.flavor_action_controller = flavor_access.FlavorActionController()
        self.req = FakeRequest()
        self.context = self.req.environ['nova.context']
        self.stubs.Set(instance_types, 'get_instance_type_by_flavor_id',
                       fake_get_instance_type_by_flavor_id)
        self.stubs.Set(instance_types, 'get_all_types', fake_get_all_types)
        self.stubs.Set(instance_types, 'get_instance_type_access_by_flavor_id',
                       fake_get_instance_type_access_by_flavor_id)

    def _verify_flavor_list(self, result, expected):
        # result already sorted by flavor_id
        self.assertEqual(len(result), len(expected))

        for d1, d2 in zip(result, expected):
            self.assertEqual(d1['id'], d2['id'])

    def test_list_flavor_access_public(self):
        # query os-flavor-access on public flavor should return 404
        req = fakes.HTTPRequest.blank('/v2/fake/flavors/os-flavor-access',
                                      use_admin_context=True)
        self.assertRaises(exc.HTTPNotFound,
                          self.flavor_access_controller.index,
                          self.req, '1')

    def test_list_flavor_access_private(self):
        expected = {'flavor_access': [
            {'flavor_id': '2', 'tenant_id': 'proj2'},
            {'flavor_id': '2', 'tenant_id': 'proj3'}]}
        result = self.flavor_access_controller.index(self.req, '2')
        self.assertEqual(result, expected)

    def test_list_flavor_with_admin_default_proj1(self):
        expected = {'flavors': [{'id': '0'}, {'id': '1'}]}
        req = fakes.HTTPRequest.blank('/v2/fake/flavors',
                                      use_admin_context=True)
        req.environ['nova.context'].project_id = 'proj1'
        result = self.flavor_controller.index(req)
        self._verify_flavor_list(result['flavors'], expected['flavors'])

    def test_list_flavor_with_admin_default_proj2(self):
        expected = {'flavors': [{'id': '0'}, {'id': '1'}, {'id': '2'}]}
        req = fakes.HTTPRequest.blank('/v2/fake/flavors',
                                      use_admin_context=True)
        req.environ['nova.context'].project_id = 'proj2'
        result = self.flavor_controller.index(req)
        self._verify_flavor_list(result['flavors'], expected['flavors'])

    def test_list_flavor_with_admin_ispublic_true(self):
        expected = {'flavors': [{'id': '0'}, {'id': '1'}]}
        req = fakes.HTTPRequest.blank('/v2/fake/flavors?is_public=true',
                                      use_admin_context=True)
        result = self.flavor_controller.index(req)
        self._verify_flavor_list(result['flavors'], expected['flavors'])

    def test_list_flavor_with_admin_ispublic_false(self):
        expected = {'flavors': [{'id': '2'}, {'id': '3'}]}
        req = fakes.HTTPRequest.blank('/v2/fake/flavors?is_public=false',
                                      use_admin_context=True)
        result = self.flavor_controller.index(req)
        self._verify_flavor_list(result['flavors'], expected['flavors'])

    def test_list_flavor_with_admin_ispublic_false_proj2(self):
        expected = {'flavors': [{'id': '2'}, {'id': '3'}]}
        req = fakes.HTTPRequest.blank('/v2/fake/flavors?is_public=false',
                                      use_admin_context=True)
        req.environ['nova.context'].project_id = 'proj2'
        result = self.flavor_controller.index(req)
        self._verify_flavor_list(result['flavors'], expected['flavors'])

    def test_list_flavor_with_admin_ispublic_none(self):
        expected = {'flavors': [{'id': '0'}, {'id': '1'}, {'id': '2'},
                                {'id': '3'}]}
        req = fakes.HTTPRequest.blank('/v2/fake/flavors?is_public=none',
                                      use_admin_context=True)
        result = self.flavor_controller.index(req)
        self._verify_flavor_list(result['flavors'], expected['flavors'])

    def test_list_flavor_with_no_admin_default(self):
        expected = {'flavors': [{'id': '0'}, {'id': '1'}]}
        req = fakes.HTTPRequest.blank('/v2/fake/flavors',
                                      use_admin_context=False)
        result = self.flavor_controller.index(req)
        self._verify_flavor_list(result['flavors'], expected['flavors'])

    def test_list_flavor_with_no_admin_ispublic_true(self):
        expected = {'flavors': [{'id': '0'}, {'id': '1'}]}
        req = fakes.HTTPRequest.blank('/v2/fake/flavors?is_public=true',
                                      use_admin_context=False)
        result = self.flavor_controller.index(req)
        self._verify_flavor_list(result['flavors'], expected['flavors'])

    def test_list_flavor_with_no_admin_ispublic_false(self):
        expected = {'flavors': [{'id': '0'}, {'id': '1'}]}
        req = fakes.HTTPRequest.blank('/v2/fake/flavors?is_public=false',
                                      use_admin_context=False)
        result = self.flavor_controller.index(req)
        self._verify_flavor_list(result['flavors'], expected['flavors'])

    def test_list_flavor_with_no_admin_ispublic_none(self):
        expected = {'flavors': [{'id': '0'}, {'id': '1'}]}
        req = fakes.HTTPRequest.blank('/v2/fake/flavors?is_public=none',
                                      use_admin_context=False)
        result = self.flavor_controller.index(req)
        self._verify_flavor_list(result['flavors'], expected['flavors'])

    def test_add_tenant_access(self):
        def stub_add_instance_type_access(flavorid, projectid, ctxt=None):
            self.assertEqual('3', flavorid, "flavorid")
            self.assertEqual("proj2", projectid, "projectid")
        self.stubs.Set(instance_types, 'add_instance_type_access',
                       stub_add_instance_type_access)
        expected = {'flavor_access':
            [{'flavor_id': '3', 'tenant_id': 'proj3'}]}
        body = {'addTenantAccess': {'tenant': 'proj2'}}
        req = fakes.HTTPRequest.blank('/v2/fake/flavors/2/action',
                                      use_admin_context=True)
        result = self.flavor_action_controller.\
            _addTenantAccess(req, '3', body)
        self.assertEqual(result, expected)

    def test_add_tenant_access_with_already_added_access(self):
        def stub_add_instance_type_access(flavorid, projectid, ctxt=None):
            raise exception.FlavorAccessExists()
        self.stubs.Set(instance_types, 'add_instance_type_access',
                       stub_add_instance_type_access)
        body = {'addTenantAccess': {'tenant': 'proj2'}}
        req = fakes.HTTPRequest.blank('/v2/fake/flavors/2/action',
                                      use_admin_context=True)
        self.assertRaises(exc.HTTPConflict,
                          self.flavor_action_controller._addTenantAccess,
                          self.req, '3', body)

    def test_remove_tenant_access_with_bad_access(self):
        def stub_remove_instance_type_access(flavorid, projectid, ctxt=None):
            self.assertEqual('3', flavorid, "flavorid")
            self.assertEqual("proj2", projectid, "projectid")
        expected = {'flavor_access': [
            {'flavor_id': '3', 'tenant_id': 'proj3'}]}
        self.stubs.Set(instance_types, 'remove_instance_type_access',
                       stub_remove_instance_type_access)
        body = {'removeTenantAccess': {'tenant': 'proj2'}}
        req = fakes.HTTPRequest.blank('/v2/fake/flavors/2/action',
                                      use_admin_context=True)
        result = self.flavor_action_controller.\
            _addTenantAccess(req, '3', body)
        self.assertEqual(result, expected)

    def test_remove_tenant_access_with_bad_access(self):
        def stub_remove_instance_type_access(flavorid, projectid, ctxt=None):
            raise exception.FlavorAccessNotFound()
        self.stubs.Set(instance_types, 'remove_instance_type_access',
                       stub_remove_instance_type_access)
        body = {'removeTenantAccess': {'tenant': 'proj2'}}
        req = fakes.HTTPRequest.blank('/v2/fake/flavors/2/action',
                                      use_admin_context=True)
        self.assertRaises(exc.HTTPNotFound,
                          self.flavor_action_controller._removeTenantAccess,
                          self.req, '3', body)


class FlavorAccessSerializerTest(test.TestCase):
    def test_xml_declaration(self):
        access_list = [{'flavor_id': '2', 'tenant_id': 'proj2'}]
        serializer = flavor_access.FlavorAccessTemplate()
        output = serializer.serialize(access_list)
        has_dec = output.startswith("<?xml version='1.0' encoding='UTF-8'?>")
        self.assertTrue(has_dec)

    def test_serializer_empty(self):
        access_list = []

        serializer = flavor_access.FlavorAccessTemplate()
        text = serializer.serialize(access_list)
        tree = etree.fromstring(text)
        self.assertEqual(len(tree), 0)

    def test_serializer(self):
        access_list = [{'flavor_id': '2', 'tenant_id': 'proj2'},
                       {'flavor_id': '2', 'tenant_id': 'proj3'}]

        serializer = flavor_access.FlavorAccessTemplate()
        text = serializer.serialize(access_list)
        tree = etree.fromstring(text)

        self.assertEqual('flavor_access', tree.tag)
        self.assertEqual(len(access_list), len(tree))

        for i in range(len(access_list)):
            self.assertEqual('access', tree[i].tag)
            self.assertEqual(access_list[i]['flavor_id'],
                             tree[i].get('flavor_id'))
            self.assertEqual(access_list[i]['tenant_id'],
                             tree[i].get('tenant_id'))
