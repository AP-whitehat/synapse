# -*- coding: utf-8 -*-
# Copyright 2018 New Vector Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import logging

from twisted.internet import defer

from synapse.api.constants import EventTypes, Membership, RoomCreationPreset
from synapse.types import create_requester
from synapse.util.caches.descriptors import cachedInlineCallbacks

logger = logging.getLogger(__name__)


class ServerNoticesManager(object):
    def __init__(self, hs):
        """

        Args:
            hs (synapse.server.HomeServer):
        """

        self._store = hs.get_datastore()
        self._config = hs.config
        self._room_creation_handler = hs.get_room_creation_handler()
        self._event_creation_handler = hs.get_event_creation_handler()

    def is_enabled(self):
        return self._config.server_notices_mxid is not None

    @defer.inlineCallbacks
    def send_notice(self, user_id, event_content):
        room_id = yield self.get_notice_room_for_user(user_id)

        system_mxid = self._config.server_notices_mxid
        requester = create_requester(system_mxid)

        logger.info("Sending server notice to %s", user_id)

        yield self._event_creation_handler.create_and_send_nonmember_event(
            requester, {
                "type": EventTypes.Message,
                "room_id": room_id,
                "sender": system_mxid,
                "content": event_content,
            },
            ratelimit=False,
        )

    @cachedInlineCallbacks()
    def get_notice_room_for_user(self, user_id):
        """Get the room for notices for a given user

        If we have not yet created a notice room for this user, create it

        Args:
            user_id (str): complete user id for the user we want a room for

        Returns:
            str: room id of notice room.
        """
        if not self.is_enabled():
            raise Exception("Server notices not enabled")

        rooms = yield self._store.get_rooms_for_user_where_membership_is(
            user_id, [Membership.INVITE, Membership.JOIN],
        )
        system_mxid = self._config.server_notices_mxid
        for room in rooms:
            user_ids = yield self._store.get_users_in_room(room.room_id)
            if system_mxid in user_ids:
                # we found a room which our user shares with the system notice
                # user
                logger.info("Using room %s", room.room_id)
                defer.returnValue(room.room_id)

        # apparently no existing notice room: create a new one
        logger.info("Creating server notices room for %s", user_id)

        requester = create_requester(system_mxid)
        info = yield self._room_creation_handler.create_room(
            requester,
            config={
                "preset": RoomCreationPreset.PRIVATE_CHAT,
                "name": self._config.server_notices_room_name,
                "power_level_content_override": {
                    "users_default": -10,
                },
                "invite": (user_id,)
            },
            ratelimit=False,
            creator_join_profile={
                "displayname": self._config.server_notices_mxid_display_name,
            },
        )
        room_id = info['room_id']

        logger.info("Created server notices room %s for %s", room_id, user_id)
        defer.returnValue(room_id)
