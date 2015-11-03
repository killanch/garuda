# -*- coding: utf-8 -*-

import redis
from bambou import NURESTRootObject
from mock import patch

from garuda.core.controllers import GACoreController, GASessionsController, GACoreController
from garuda.core.plugins import GAAuthenticationPlugin
from garuda.core.models import GASession, GAPluginManifest
from garuda.tests import UnitTestCase


class FakeAuthPlugin(GAAuthenticationPlugin):

    @classmethod
    def manifest(self):
        return GAPluginManifest(name='test.fake.auth', version=1.0, identifier="test.fake.auth")

    def authenticate(self, request=None, session=None):
        root = NURESTRootObject()
        root.id = "bbbbbbbb-f93e-437d-b97e-4c945904e7bb"
        root.api_key = "aaaaaaaa-98d4-4c2b-a136-770c9cbf7cdc"
        root.user_name = "Test"
        return root

    def should_manage(self, request):
        """
        """
        return True

    def get_session_identifier(self, request):
        """
        """
        return request.token


class GASessionsControllerTestCase(UnitTestCase):
    """
    """
    def __init__(self, name):
        """
        """
        super(GASessionsControllerTestCase, self).__init__(name)
        redis_connection = redis.StrictRedis()

        self.fake_auth_plugin = FakeAuthPlugin()
        self.core_controller = GACoreController(garuda_uuid='test-garuda', redis_info={'host': '127.0.0.1', 'port': '6379', 'db': 5}, authentication_plugins=[self.fake_auth_plugin])

        self.sessions_controller = self.core_controller.sessions_controller
        self.sessions_controller._default_session_ttl = 3

    def setUp(self):
        """ Initialize context
        """
        self.core_controller.start()

    def tearDown(self):
        """ Cleanup context
        """
        self.core_controller.stop()

    def test_create_session(self):
        """ Create a session with authentication success should succeed
        """
        session = self.sessions_controller.create_session(request='fake-request')
        self.assertEquals(len(session.uuid), 36)
        self.assertEquals(session.garuda_uuid, self.sessions_controller._garuda_uuid)

    def test_create_session_without_authentication(self):
        """ Create a session with authentication failure should succeed
        """
        with patch.object(self.fake_auth_plugin, 'authenticate', return_value=None) as mock_method:
            session = mock_method()

        self.assertEquals(session, None)

    def test_get_existing_session(self):
        """ Get a session with existing uuid should return the session
        """
        session = self.sessions_controller.create_session(request='fake-request')
        self.assertEquals(self.sessions_controller.get_session(session.uuid).to_dict(), session.to_dict())

    def test_get_unknown_session(self):
        """ Get a session with unknown uuid should return None
        """
        session = self.sessions_controller.get_session('0000-000-0000000-00000')
        self.assertEquals(session, None)

    def test_create_session(self):
        """ Create a new session should insert data in redis db
        """
        session = self.sessions_controller.create_session(request='fake-request')
        self.assertEquals(session.uuid, self.sessions_controller.get_session(session.uuid).uuid)

    def test_delete_session(self):
        """ Delete a session should clean the redis db
        """
        session = self.sessions_controller.create_session(request='fake-request')
        self.sessions_controller.delete_session(session)
        self.assertEquals(self.sessions_controller.get_session(session.uuid), None)

    def test_local_sessions(self):
        """ Ensure asking for local garuda session only returns local one
        """
        not_session = GASession(garuda_uuid='not-garuda')

        session = self.sessions_controller.create_session(request='fake-request')
        self.assertIn(session.uuid, [session.uuid for session in self.sessions_controller.get_all_local_sessions()])
        self.assertNotIn(session.uuid, [not_session.uuid for session in self.sessions_controller.get_all_local_sessions()])

    def test_flushing_local_sets_does_not_remove_sessions(self):
        """ Cleaning a garuda should only clean the session sets, not the sessions
        """
        session = self.sessions_controller.create_session(request='fake-request')
        self.sessions_controller.flush_local_sessions()
        self.assertIsNotNone(self.sessions_controller.get_session(session.uuid))

    def test_set_session_to_listening_status(self):
        """ Setting a session to listening state should update the value in redis db to True
        """
        session = self.sessions_controller.create_session(request='fake-request')
        self.sessions_controller.set_session_listening_status(session, True)
        self.assertIn(session.uuid, [session.uuid for session in self.sessions_controller.get_all_local_sessions(listening=True)])

    def test_unset_session_to_listening_status(self):
        """ Unsetting the a session listening state should update the value in redis db to False
        """
        session = self.sessions_controller.create_session(request='fake-request')
        self.sessions_controller.set_session_listening_status(session, False)
        self.assertNotIn(session, self.sessions_controller.get_all_local_sessions(listening=True))

    def test_getting_local_listening_sessions(self):
        """ Getting local listening session should only return local listening sessions
        """
        session1 = self.sessions_controller.create_session(request='fake-request')
        session2 = self.sessions_controller.create_session(request='fake-request')
        session3 = self.sessions_controller.create_session(request='fake-request')

        self.sessions_controller.set_session_listening_status(session1, True)
        self.sessions_controller.set_session_listening_status(session2, True)

        self.assertIn(session1.uuid, [session.uuid for session in self.sessions_controller.get_all_local_sessions(listening=True)])
        self.assertIn(session2.uuid, [session.uuid for session in self.sessions_controller.get_all_local_sessions(listening=True)])
        self.assertNotIn(session3.uuid, [session.uuid for session in self.sessions_controller.get_all_local_sessions(listening=True)])

    def test_expire_propagation(self):
        """ Ensure that when a session key expires, it is correctly removed from the session sets (test sleeps 1.5 sec)
        """
        self.sessions_controller._default_session_ttl = 1
        session = self.sessions_controller.create_session(request='fake-request')

        self.sessions_controller.set_session_listening_status(session, True)

        self.assertIn(session.uuid, [session.uuid for session in self.sessions_controller.get_all_local_sessions()])
        self.assertIn(session.uuid, [session.uuid for session in self.sessions_controller.get_all_local_sessions(listening=True)])

        import time
        time.sleep(1.5)

        self.assertNotIn(session.uuid, [session.uuid for session in self.sessions_controller.get_all_local_sessions()])
        self.assertNotIn(session.uuid, [session.uuid for session in self.sessions_controller.get_all_local_sessions(listening=True)])

    def test_flush_all_sessions(self):
        """ Test flushing all sessions leaves no trace
        """
        session = self.sessions_controller.create_session(request='fake-request')
        self.sessions_controller.flush_local_sessions()
        self.assertEquals(self.sessions_controller.get_all_local_sessions(listening=True), [])


