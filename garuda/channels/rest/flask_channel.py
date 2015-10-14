# -*- coding: utf-8 -*-

import json
import logging
import time
import signal
import sys
from base64 import urlsafe_b64decode
from copy import deepcopy
from uuid import uuid4

from flask import Flask, request, make_response

from garuda.core.lib import SDKLibrary
from garuda.core.models import GAError, GAPluginManifest, GAPushNotification, GARequest, GAResponseFailure, GAResponseSuccess
from garuda.core.channels import GAChannel

from .constants import RESTConstants
from .parser import PathParser

logger = logging.getLogger('garuda.comm.flask')


class GAFlaskChannel(GAChannel):
    """

    """

    @classmethod
    def manifest(cls):
        """
        """
        return GAPluginManifest(name='rest', version=1.0, identifier="garuda.communicationchannels.flask")

    def __init__(self, host='0.0.0.0', port=3000, push_timeout=60):
        """
        """
        # mute flask logging for now
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        self._uuid = str(uuid4())
        self._controller = None
        self._host = host
        self._port = port
        self._push_timeout = push_timeout

        self._flask = Flask(self.__class__.__name__)
        self._flask.add_url_rule('/<path:path>/events', 'events', self._handle_event_request, methods=[RESTConstants.HTTP_GET], strict_slashes=False, defaults={'path': ''})
        self._flask.add_url_rule('/<path:path>', 'models', self._handle_model_request, methods=[RESTConstants.HTTP_GET, RESTConstants.HTTP_POST, RESTConstants.HTTP_PUT, RESTConstants.HTTP_DELETE, RESTConstants.HTTP_HEAD, RESTConstants.HTTP_OPTIONS], strict_slashes=False)

    def set_core_controller(self, core_controller):
        """
        """
        self.core_controller = core_controller

    def did_fork(self):
        """
        """
        self.core_controller.start()

    def run(self):
        """
        """
        self._api_prefix = SDKLibrary().get_sdk('default').SDKInfo.api_prefix()

        logger.info("Communication channel listening on %s:%d" % (self._host, self._port))

        def handle_signal(signal_number, frame_stack):
            self.core_controller.stop()
            sys.exit(0)

        signal.signal(signal.SIGTERM, handle_signal)

        self._flask.run(host=self._host, port=self._port, threaded=True, debug=True, use_reloader=False)

        while True:
            time.sleep(30000)

    def _handle_model_request(self, path):
        """
        """
        content = self._extract_content(request)
        username, token = self._extract_auth(request.headers)
        parameters = self._extract_parameters(request.headers)
        filter = self._extract_filter(request.headers)
        page, page_size = self._extract_paging(request.headers)
        order_by = self._extract_ordering(request.headers)

        method = request.method.upper()

        logger.info('> %s %s from %s' % (request.method, request.path, parameters['Host']))
        logger.debug(json.dumps(parameters, indent=4))

        parser = PathParser()
        resources = parser.parse(path=path, url_prefix="%s/" % SDKLibrary().get_sdk('default').SDKInfo.api_prefix())

        action = self.determine_action(method, resources)

        ga_request = GARequest( action=action,
                                content=content,
                                parameters=parameters,
                                resources=resources,
                                username=username,
                                token=token,
                                filter=filter,
                                page=page,
                                page_size=page_size,
                                order_by=order_by,
                                channel=self)

        ga_response = self.core_controller.execute_model_request(request=ga_request)

        logger.info('< %s %s to %s' % (request.method, request.path, parameters['Host']))
        # logger.debug(json.dumps(content, indent=4))

        return self.make_http_response(action=action, response=ga_response)

    def _handle_event_request(self, path):
        """
        """
        content = self._extract_content(request)
        parameters = self._extract_parameters(request.headers)
        username, token = self._extract_auth(request.headers)

        logger.info('= %s %s from %s' % (request.method, request.path, parameters['Host']))
        # logger.debug(json.dumps(parameters, indent=4))

        ga_request = GARequest( action=GARequest.ACTION_LISTENEVENTS,
                                content=content,
                                parameters=parameters,
                                username=username,
                                token=token,
                                channel=self)

        session, ga_response_failure = self.core_controller.execute_events_request(request=ga_request)

        if ga_response_failure:
            self.make_http_response(action=GARequest.ACTION_READ, response=ga_response_failure)
            return

        events = []

        self.core_controller.sessions_controller.set_session_listening_status(session=session, status=True)

        for event in self.core_controller.push_controller.get_next_event(session=session):
            events.append(event)

        ga_notification = GAPushNotification(events=events)
        logger.info('< %s %s events to %s' % (request.method, request.path, parameters['Host']))

        self.core_controller.sessions_controller.set_session_listening_status(session=session, status=False)

        return self.make_notification_response(notification=ga_notification)

    def _extract_content(self, request):
        """

        """
        content = request.get_json(force=True, silent=True)
        if content:
            return deepcopy(content)

        return dict()

    def _extract_auth(self, headers):
        """
        """
        username = None
        token = None

        if 'Authorization' in headers:
            encoded_auth = headers['Authorization'][6:]  # XREST stuff
            decoded_auth = urlsafe_b64decode(str(encoded_auth))
            auth = decoded_auth.split(':')
            username = auth[0]
            token = auth[1]

        return username, token

    def _extract_parameters(self, headers):
        """
        """
        params = {}

        for p in headers:
            params[p[0]] = p[1]

        return params

    def _convert_errors(self, action, response):
        """
        """
        properties = {}
        error_type = response.content[0].type if len(response.content) > 0 else None

        for error in response.content:
            if error.property_name not in properties:
                properties[error.property_name] = {
                    "property": error.property_name,
                    "type": error.type,
                    "descriptions": []}

            properties[error.property_name]["descriptions"].append(error.to_dict())

        if error_type == GAError.TYPE_INVALID:
            code = 400

        elif error_type == GAError.TYPE_UNAUTHORIZED:
            code = 401

        elif error_type == GAError.TYPE_AUTHENTICATIONFAILURE:
            code = 403

        elif error_type == GAError.TYPE_NOTFOUND:
            code = 404

        elif error_type == GAError.TYPE_NOTALLOWED:
            code = 405

        elif error_type == GAError.TYPE_CONFLICT:
            code = 409

        else:
            code = 520

        return (code, {"errors": properties.values()})

    def _convert_content(self, action, response):
        """
        """
        if type(response.content) is list:
            content = [obj.to_dict() for obj in response.content]

        elif hasattr(response.content, 'to_dict'):
            content = [response.content.to_dict()]

        else:
            content = str(response.content)

        if action is GARequest.ACTION_CREATE:
            code = 201

        elif content is None:
            code = 204

        else:
            code = 200

        return (code, content)

    def _extract_filter(self, headers):
        """
        """
        if 'X-Filter' in headers:
            return headers['X-Filter']

        if 'X-Nuage-Filter' in headers:
            return headers['X-Nuage-Filter']

        return None

    def _extract_paging(self, headers):
        """
        """
        page = None
        page_size = 500

        if 'X-Nuage-Page' in headers:
            page = headers['X-Nuage-Page']

        if 'X-Nuage-PageSize' in headers:
            page_size = headers['X-Nuage-PageSize']

        return page, page_size

    def _extract_ordering(self, headers):
        """
        """
        if 'X-OrderBy' in headers:
            return headers['X-OrderBy']

        if 'X-Nuage-OrderBy' in headers:
            return headers['X-Nuage-OrderBy']

    def make_http_response(self, action, response):
        """
        """
        if isinstance(response, GAResponseSuccess):
            code, content = self._convert_content(action, response)

        else:
            code, content = self._convert_errors(action, response)

        logger.debug(json.dumps(content, indent=4))

        flask_response = make_response(json.dumps(content))
        flask_response.status_code = code
        flask_response.mimetype = 'application/json'

        if response.total_count is not None:
            flask_response.headers['X-Nuage-Count'] = response.total_count

        if response.page is not None:
            flask_response.headers['X-Nuage-Page'] = response.page
        else:
            flask_response.headers['X-Nuage-Page'] = -1

        if response.page_size is not None:
            flask_response.headers['X-Nuage-PageSize'] = response.page_size

        return flask_response

    def make_notification_response(self, notification):
        """
        """
        content = notification.to_dict()

        logger.debug(json.dumps(content, indent=4))

        response = make_response(json.dumps(content))
        response.status_code = 200
        response.mimetype = 'application/json'

        return response

    def determine_action(self, method, resources):
        """
        """
        if method == RESTConstants.HTTP_POST:
            return GARequest.ACTION_CREATE

        elif method == RESTConstants.HTTP_PUT:
            if len(resources) == 2:  # this is a PUT /A/id/B, which means this is an membership relationship
                return GARequest.ACTION_ASSIGN
            else:
                return GARequest.ACTION_UPDATE

        elif method == RESTConstants.HTTP_DELETE:
            return GARequest.ACTION_DELETE

        elif method == RESTConstants.HTTP_HEAD:
            return GARequest.ACTION_COUNT

        elif method in [RESTConstants.HTTP_GET, RESTConstants.HTTP_OPTIONS]:
            if resources[-1].value is None:
                return GARequest.ACTION_READALL

            else:
                return GARequest.ACTION_READ

        raise Exception("Unknown action. This should never happen")