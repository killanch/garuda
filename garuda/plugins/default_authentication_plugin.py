# -*- coding: utf-8 -*-

import logging
logger = logging.getLogger('Garuda.plugins.DefaultAuthenticationPlugin')

from garuda.core.lib import SDKsManager
from garuda.core.plugins import GAAuthenticationPlugin
from garuda.core.config import GAConfig


class DefaultAuthenticationPlugin(GAAuthenticationPlugin):
    """
    """

    def should_manage(self, request):
        """
        """
        return True

    def authenticate(self, request):
        """
        """

        if 'username' not in request.parameters or \
           'password' not in request.parameters or \
           'X-Nuage-Organization' not in request.parameters:
           logger.debug("No information provided to authenticate user")
           return None

        username = request.parameters['username']
        password = request.parameters['password']
        enterprise = request.parameters['X-Nuage-Organization']

        logger.debug("Authenticate user with username=%s, password=%s, enterprise=%s" % (username, password, enterprise))

        sdks_manager = SDKsManager()
        sdk_session_class = sdks_manager.get_sdk_session_class('vspk32')
        session = sdk_session_class(username=username, password=password, enterprise=enterprise, api_url=GAConfig.VSD_API_URL)
        session.start()

        return session.user

