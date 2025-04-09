import random

from typing import List, Dict
from logging import Logger

from ask_sdk_model import Response
from ask_sdk_model.interfaces.audioplayer import AudioItem, Stream, AudioItemMetadata, PlayDirective, PlayBehavior, StopDirective
from ask_sdk_model.interfaces import display

from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.utils import get_slot_value_v2

from plexapi.audio import Track
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound

from . import config
from . import prompts

class Controller:
    """
    Controller class for managing playlist and playback operations.
    Attributes:
        logger (Logger): Logger instance for logging debug and info messages.
        handler_input (HandlerInput): HandlerInput instance for managing request and response attributes.
    Methods:
        add_track(track: Dict) -> None:
            Adds a track to the playlist.
        get_next_track(update_index: bool) -> Dict:
            Retrieves the next track in the playlist.
        get_prevous_track() -> Dict:
            Retrieves the previous track in the playlist.
        get_current_track() -> Dict:
            Retrieves the current track in the playlist.
        shuffle_play_order(shuffle: bool) -> None:
            Shuffles the playback order of the playlist based on the shuffle parameter.
        clear_playlist() -> None:
            Clears the current playlist and resets playback settings.
        track_to_audio_item(track: Dict, offset: int, previous_token: str) -> AudioItem:
            Converts a track (Dict) to an AudioItem object.
        resume_playback() -> Response:
            Handles the resume command.
        start_playback() -> Response:
            Handles the start over command.
        pause_playback() -> Response:
            Handles the pause command.
        previous_playback() -> Response:
            Handles the previous track command.
        next_playback() -> Response:
            Handles the next track command.
        loop_playback(enable: bool) -> Response:
            Enables or disables loop mode.
        shuffle_playback(enable: bool) -> Response:
            Enables or disables shuffle mode.
        retrieve_track_details() -> Response:
            Retrieves track details to the user.
        playback_started() -> Response:
            Handles the event when playback is started.
        playback_stopped() -> Response:
            Handles the event when playback is stopped.
        playback_nearly_finished() -> Response:
            Handles the event when playback is nearly finished.
        playback_finished() -> Response:
            Handles the event when playback is finished.
        playback_failed() -> Response:
            Handles the playback failure scenario.
        load_music_section() -> Response:
            Connects to a plex media server and loads the music section.
        set_playlist_name(name: str) -> None:
            Sets the playlist name used by alexa.
        add_plex_track(plex_track: Track) -> None:
            Adds a track (Track object) to the playlist.
        add_plex_tracks(plex_track_list: List[Track]) -> None:
            Adds a list of tracks (Track objects) to the playlist.
        play_random_music() -> Response:
            Plays random music.
        play_music_by_artist() -> Response:
            Plays music by a given artist.
        play_song_by_artist() -> Response:
            Plays a specific song by a given artist.
        play_album_by_artist() -> Response:
            Plays a specific album by a given artist.
        play_music_by_genre() -> Response:
            Plays music by a given genre.
        play_playlist() -> Response:
            Plays a Plex playlist.
    """
    def __init__(self, logger : Logger, handler_input : HandlerInput) -> None:
        """
        Initializes the controller with a logger and the handler input instance.
        Args:
            logger (Logger): The logger instance to be used for logging.
            handler_input (HandlerInput): The handler input instance.
        """

        self.logger = logger
        """Logger"""

        self.handler_input = handler_input
        """handler_input"""


#
# Playlist utils
#
    def add_track(self, track: Dict) -> None:
        """
        Adds a track to the playlist.
        Args:
            track (Dict): The track information
        Returns:
            None
        """

        self.logger.debug('In add_track()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        playlist_len = len(playback_info["playlist"])

        playback_info["playlist"][str(playlist_len)] = track
        playback_info["play_order"].append(playlist_len)


    def get_next_track(self, update_index: bool) -> Dict:
        """
        Retrieves the next track in the playlist.
        Returns:
            Dict: The next track information
        """

        self.logger.debug('In get_next_track()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes
        playback_setting = persistence_attr.get("playback_setting")
        playback_info = persistence_attr.get("playback_info")

        index = int(playback_info["index"])
        playlist_len = len(playback_info["playlist"])

        if playlist_len == 0 or (index == (playlist_len - 1) and not playback_setting["loop"]):
            return None

        index = (index + 1) % playlist_len

        if update_index:
            playback_info["index"] = index
            playback_info["offset_in_ms"] = 0
            playback_info["playback_index_changed"] = True

        play_order = playback_info["play_order"]
        return playback_info["playlist"].get(str(play_order[index]))


    def get_prevous_track(self) -> Dict:
        """
        Retrieves the previous track in the playlist.
        Returns:
            Dict: The previous track information
        """

        self.logger.debug('In get_prevous_track()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes
        playback_setting = persistence_attr.get("playback_setting")
        playback_info = persistence_attr.get("playback_info")

        index = int(playback_info["index"])
        playlist_len = len(playback_info["playlist"])

        if playlist_len == 0 or (index == 0 and not playback_setting["loop"]):
            return None

        index = (index - 1) if index > 0 else (playlist_len - 1)

        playback_info["index"] = index
        playback_info["offset_in_ms"] = 0
        playback_info["playback_index_changed"] = True

        play_order = playback_info["play_order"]
        return playback_info["playlist"].get(str(play_order[index]))


    def get_current_track(self) -> Dict:
        """
        Retrieves the current track information
        Returns:
            Dict: The current track information
        """

        self.logger.debug('In get_current_track()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        index = int(playback_info["index"])
        playlist_len = len(playback_info["playlist"])

        if index < playlist_len:
            play_order = playback_info["play_order"]
            return playback_info["playlist"].get(str(play_order[index]))


    def shuffle_play_order(self, shuffle: bool) -> None:
        """
        Adjusts the playback order of the playlist based on the shuffle parameter.
        If shuffle is True, the playback order is randomized, with the current index
        being moved to the start of the new order. If shuffle is False, the playback
        order is reset to the original order.
        Args:
            shuffle (bool): A flag indicating whether to shuffle the playback order.
        Returns:
            None
        """

        self.logger.debug('In shuffle_play_order()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        index = int(playback_info["index"])
        play_order = playback_info["play_order"]
        playlist_index = int(play_order[index])
        playlist_len = len(playback_info["playlist"])

        play_order = [l for l in range(0, playlist_len)]

        if shuffle:
            play_order.pop(index)
            random.shuffle(play_order)
            play_order.insert(0, index)
            index = 0
        else:
            index = playlist_index

        playback_info["play_order"] = play_order
        playback_info["index"] = index
        playback_info["playback_index_changed"] = True


    def clear_playlist(self) -> None:
        """
        Clears the current playlist and resets playback settings.
        This method performs the following actions:
        - Disables shuffle and loop settings.
        - Resets the playback index and offset.
        - Marks the playback index as changed.
        - Clears the playlist.
        Returns:
            None
        """

        self.logger.debug('In clear_playlist()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes
        playback_setting = persistence_attr.get("playback_setting")
        playback_info = persistence_attr.get("playback_info")

        playback_setting["shuffle"] = False
        playback_setting["loop"] = False

        playback_info["index"] = 0
        playback_info["offset_in_ms"] = 0
        playback_info["playback_index_changed"] = True
        playback_info["playlist"] = {}
        playback_info["play_order"] = []


#
# Playback control
#
    def track_to_audio_item(self, track: Dict, offset: int, previous_token: str) -> AudioItem:
        """
        Converts a track (Dict) to an AudioItem object.
        Args:
            track (Dict): A dictionary containing track information with keys "title", "artist", "album", "album_art", "artist_art", "id", and "uri".
            offset (int): The offset in milliseconds for the audio stream.
            previous_token (str): The expected previous token for the audio stream.
        Returns:
            AudioItem: An object containing the audio stream and metadata for the track.
        """

        self.logger.debug('In track_to_audio_item()')

        metadata = AudioItemMetadata(
            title = track["title"],
            subtitle = track["artist"]
        )        
        if track["album_art"] is not None:
            metadata.art=display.Image(
                content_description = track["album"],
                sources=[
                    display.ImageInstance(
                        url=track["album_art"]
                    )
                ]
            )
        if track["artist_art"] is not None:
            metadata.background_image=display.Image(
                content_description = track["artist"],
                sources = [
                    display.ImageInstance(
                        url = track["artist_art"]
                    )
                ]
            )

        stream = Stream(token=track["id"], url=track["uri"], offset_in_milliseconds=offset, expected_previous_token=previous_token)
        return AudioItem(stream=stream, metadata=metadata)


    def resume_playback (self) -> Response:
        """
        Handles the resume command.
        This method resumes playback with the saved offset.
        Returns:
            Response: The response object with the play directive and the current track
            in audio item format. If there is no current track, the response object is empty.
        """

        self.logger.debug('In resume_playback()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        current_track = self.get_current_track()

        playback_info['next_stream_enqueued'] = False


        directive = PlayDirective(play_behavior=PlayBehavior.REPLACE_ALL, audio_item=self.track_to_audio_item(current_track, int(playback_info["offset_in_ms"]), None))
        self.handler_input.response_builder.add_directive(directive).set_should_end_session(True)

        return self.handler_input.response_builder.response


    def start_playback (self) -> Response:
        """
        Handles the start over command.
        This method resets the offset of the current track and then resumes playback.
        Returns:
            Response: The response object with the play directive and the current track
            in audio item format. If there is no current track, the response object is empty.
        """

        self.logger.debug('In start_playback()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        playback_info["offset_in_ms"] = 0

        return self.resume_playback()


    def pause_playback (self) -> Response:
        """
        Handles the pause command.
        Returns:
            Response: The response object with the stop directive.
        """
        self.logger.debug('In pause_playback()')

        self.handler_input.response_builder.add_directive(StopDirective()).set_should_end_session(True)
        return self.handler_input.response_builder.response


    def previous_playback (self) -> Response:
        """
        Handles the previous track command.
        Returns:
            Response: The response object with the play directive and the previous track
            in audio item format. If there are no more tracks, the response object is empty.
        """

        self.logger.debug('In previous_playback()')

        prevous_track = self.get_prevous_track()
        if prevous_track == None:
            return self.handler_input.response_builder.response

        directive = PlayDirective(play_behavior=PlayBehavior.REPLACE_ALL, audio_item=self.track_to_audio_item(prevous_track, 0, None))
        self.handler_input.response_builder.add_directive(directive).set_should_end_session(True)

        return self.handler_input.response_builder.response


    def next_playback (self) -> Response:
        """
        Handles the next track command.
        Returns:
            Response: The response object with the play directive and the next track
            in audio item format. If there are no more tracks, the response object is empty.
        """

        self.logger.debug('In next_playback()')

        next_track = self.get_next_track(True)
        if next_track == None:
            return self.handler_input.response_builder.response

        self.logger.debug(f'next_track: {next_track["title"]} by {next_track["artist"]}')

        directive = PlayDirective(play_behavior=PlayBehavior.REPLACE_ALL, audio_item=self.track_to_audio_item(next_track, 0, None))
        self.handler_input.response_builder.add_directive(directive).set_should_end_session(True)

        return self.handler_input.response_builder.response


    def loop_playback(self, enable: bool) -> Response:
        """
        Toggles playlist loop.
        Args:
            enable (bool): If True, enables the loop. If False, disables it.
        Returns:
            Response: The response object with no output speech.
        """

        self.logger.debug('In loop_playback()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes
        playback_setting = persistence_attr.get("playback_setting")

        playback_setting["loop"] = enable

        return self.handler_input.response_builder.response


    def shuffle_playback(self, enable: bool) -> Response:
        """
        Toggles shuffle playback mode.
        Args:
            enable (bool): If True, shuffles the playlist. If False, re-sorts it.
        Returns:
            Response: The response object with no output speech.
        """

        self.logger.debug('In shuffle_playback()')

        self.shuffle_play_order(enable)

        return self.handler_input.response_builder.response


    def retrieve_track_details (self) -> Response:
        """
        Retrieves the details of the current track.
        Returns:
            Response: The response object containing the spoken output with the track details.
        """

        self.logger.debug('In retrieve_track_details()')

        # get localization data
        data = self.handler_input.attributes_manager.request_attributes["_"]

        # Get the current track
        current_track = self.get_current_track()

        # Ignore the request if there is no track
        if current_track == None:
            return self.handler_input.response_builder.response

        speak_output = data[prompts.SKILL_SONG_DETAILS].format(song=current_track["title"], artist=current_track["artist"])
        self.logger.info(speak_output)

        self.handler_input.response_builder.speak(speak_output).set_should_end_session(True)
        return self.handler_input.response_builder.response


#
# Playback events
#
    def playback_started (self) -> Response:
        """
        Handles the event when playback is started.
        This method only sets the playback session and returns the response.
        Returns:
            Response: The response object with no output speech.
        """

        self.logger.debug('In playback_started()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        playback_info["in_playback_session"] = True

        return self.handler_input.response_builder.response


    def playback_stopped (self) -> Response:
        """
        Handles the event when playback is stopped.
        This method only saves the playback offset and returns the response.
        Returns:
            Response: The response object with no output speech.
        """

        self.logger.debug('In playback_stopped()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        playback_info["offset_in_ms"] = self.handler_input.request_envelope.request.offset_in_milliseconds

        return self.handler_input.response_builder.response


    def playback_nearly_finished (self) -> Response:
        """
        Handles the event when playback is nearly finished.
        This method retrieves the next track and queues it for playback.
        Returns:
            Response: The response object with the enqueue directive and the next track
            in audio item format. If there are no more tracks, the response object is empty.
        """

        self.logger.debug('In playback_nearly_finished()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        if playback_info.get("next_stream_enqueued"):
            return self.handler_input.response_builder.response

        next_track = self.get_next_track(False)
        if next_track == None:
            return self.handler_input.response_builder.response

        current_track = self.get_current_track()
        playback_info["next_stream_enqueued"] = True
        self.logger.info(f'Queuing next track: {next_track["title"]} by {next_track["artist"]}')

        directive = PlayDirective(play_behavior=PlayBehavior.ENQUEUE, audio_item=self.track_to_audio_item(next_track, 0, current_track["id"]))
        self.handler_input.response_builder.add_directive(directive).set_should_end_session(True)

        return self.handler_input.response_builder.response


    def playback_finished (self) -> Response:
        """
        Handles the event when playback is finished.
        This method only updates the next playback index (the enqueue is already
        done in the PlaybackNearlyFinishedHandler), resets the playback_session and
        next_stream_enqueued flags and sets the track's offset to 0.
        Returns:
            Response: The response object with no output speech.
        """

        self.logger.debug('In playback_finished()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        # get next track just to update the index
        next_track = self.get_next_track(True)
        if next_track == None:
            return self.handler_input.response_builder.response

        playback_info["in_playback_session"] = False
        playback_info["next_stream_enqueued"] = False
        playback_info["offset_in_ms"] = 0

        self.logger.info(f'Next track: {next_track["title"]} by {next_track["artist"]} updated')
        return self.handler_input.response_builder.response


    def playback_failed (self) -> Response:
        """
        Handles the playback failure scenario
        This method is called when a playback failure occurs. It logs the event,
        and tries with the next track in the queue.
        Returns:
            Response: The response object with no output speech.
        """

        self.logger.debug('In playback_failed()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes

        return self.next_playback()

#
# Plex API utils
#
    def load_music_section (self) -> Response:
        """
        Loads the music section from the Plex server.
        This method attempts to connect to the Plex server using the provided
        configuration and retrieves the default music section. If the section
        is not found or there is a connection error, it handles the exceptions
        and returns an appropriate response.
        Returns:
            Response: The response object containing the speech output in case of error,
            otherwize returns None.
        """

        self.logger.debug('In load_music_section()')

        # get localization data
        data = self.handler_input.attributes_manager.request_attributes["_"]

        try:
            self.plex_server = PlexServer(config.PMS_SERVER_URL, config.PMS_SERVER_TOKEN)
            self.section = self.plex_server.library.section(config.PMS_DEFAULT_SECTION_NAME)
        except NotFound  as exception:
            speak_output = data[prompts.PMS_SECTION_NOT_FOUND]
            self.logger.error(exception)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response
        except Exception as exception:
            speak_output = data[prompts.PMS_CONNECTION_ERROR]
            self.logger.error(exception)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response


    def set_playlist_name(self, name: str) -> None:
        """
        Sets the playlist name in the persistent attributes.

        Args:
            name (str): The name of the playlist to be set.

        Returns:
            None
        """

        self.logger.debug('In set_playlist_name()')
        persistence_attr = self.handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")
        playback_info["playlist_name"] = name


    def add_plex_track(self, plex_track: Track) -> None:
        """
        Adds a Plex track to the playlist.
        Args:
            plex_track (Track): The Plex track to be added. It should be an instance of the Track class.
        Returns:
            None
        """

        self.logger.debug('In add_plex_track()')
        track = {
                "id": str(plex_track.ratingKey),
                "title": plex_track.title,
                "artist": plex_track.grandparentTitle,
                "artist_art": plex_track.url(plex_track.grandparentArt),
                "album": plex_track.parentTitle,
                "album_art": plex_track.url(plex_track.parentThumb),
                "uri": plex_track.getStreamURL().replace("m3u8", "mp3")
                }

        self.add_track(track)


    def add_plex_tracks(self, plex_track_list: List[Track]) -> None:
        """
        Adds a list of Plex tracks to the playlist.
        Args:
            plex_track_list (List[Track]): A list of Plex track objects to be added.
        Returns:
            None
        """

        self.logger.debug('In add_plex_tracks()')
        for plex_track in plex_track_list:
            self.add_plex_track(plex_track)

#
# Plex API control
#
    def play_random_music (self) -> Response:
        """
        Plays a random selection of music tracks.
        This method searches for random tracks. If no tracks are found or an error
        occurs during the search, an appropriate response is returned. Otherwise,
        it clears the current playlist, adds the found tracks to the playlist, sets
        the playlist name, and starts playback.
        Returns:
            Response: The response object containing the result of the playback action.
        """

        self.logger.debug('In play_random_music()')

        # get localization data
        data = self.handler_input.attributes_manager.request_attributes["_"]

        # Get the music section
        response = self.load_music_section()
        if response is not None:
            return response

        # Search for random tracks
        try:
            plex_track_list = self.section.searchTracks(sort='random', maxresults=config.PMS_DEFAULT_MAX_RESULTS)
        except Exception as exception:
            speak_output = data[prompts.PMS_CONNECTION_ERROR]
            self.logger.error(exception)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        if len(plex_track_list) == 0:
            speak_output = data[prompts.PMS_TRACKS_SEARCH_EMPTY]
            self.logger.error(speak_output)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        self.clear_playlist()
        self.add_plex_tracks(plex_track_list)

        playlist_name = data[prompts.PMS_PLNAME_RANDOM_MUSIC]
        self.set_playlist_name(playlist_name)
        speak_output = data[prompts.PMS_PLAYING].format(playlist_name)

        self.handler_input.response_builder.speak(speak_output)
        self.logger.info(speak_output)

        return self.start_playback()


    def play_music_by_artist (self) -> Response:
        """
        Plays a music selection by a specified artist.
        This method searches for music by the specified artist, sorted by popularity
        if available in the plex media server. If no tracks are found or an error
        occurs during the search, an appropriate response is returned. Otherwise,
        it clears the current playlist, adds the found tracks to the playlist, sets
        the playlist name, and starts playback.
        Returns:
            Response: The response object containing the result of the playback action.
        """

        self.logger.debug('In play_music_by_artist()')

        # get localization data
        data = self.handler_input.attributes_manager.request_attributes["_"]

        # Get variable(s) from intent
        artist = get_slot_value_v2(self.handler_input, 'artist')
        if artist is None:
            speak_output = data[prompts.SKILL_INTENT_SLOTS_MISSING]
            self.logger.error(speak_output)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        # Get the music section
        response = self.load_music_section()
        if response is not None:
            return response

        # Search for the artist
        try:
            artist_results = self.section.searchArtists(title=artist.value)
        except Exception as exception:
            speak_output = data[prompts.PMS_ARTIST_SEARCH_ERROR].format(artist.value)
            self.logger.error(exception)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        if len(artist_results) == 0:
            speak_output = data[prompts.PMS_ARTIST_SEARCH_EMPTY].format(artist.value)
            self.logger.error(speak_output)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        # Get a list the popular tracks by the artist
        plex_track_list = artist_results[0].popularTracks()
        if len(plex_track_list) == 0:
            # No popular tracks, so look for any tracks
            plex_track_list = artist_results[0].tracks()
            if len(plex_track_list) == 0:
                speak_output = data[prompts.PMS_TRACKS_SEARCH_EMPTY]
                return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        self.clear_playlist()
        self.add_plex_tracks(plex_track_list)

        playlist_name = data[prompts.PMS_PLNAME_MUSIC_BY_ARTIST].format(artist.value)
        self.set_playlist_name(playlist_name)
        speak_output = data[prompts.PMS_PLAYING].format(playlist_name)

        self.handler_input.response_builder.speak(speak_output)
        self.logger.info(speak_output)
        return self.start_playback()


    def play_song_by_artist (self) -> Response:
        """
        Play a specific song by a given artist.
        This method searches the specific song. If no track is found or an error
        occurs during the search, an appropriate response is returned. Otherwise,
        it clears the current playlist, adds the found tracks to the playlist, sets
        the playlist name, and starts playback.
        Returns:
            Response: The response object containing the result of the playback action.
        """

        self.logger.debug('In play_song_by_artist()')

        # get localization data
        data = self.handler_input.attributes_manager.request_attributes["_"]

        # Get variable(s) from intent
        artist = get_slot_value_v2(self.handler_input, 'artist')
        song = get_slot_value_v2(self.handler_input, 'song')
        if artist is None or song is None:
            speak_output = data[prompts.SKILL_INTENT_SLOTS_MISSING]
            self.logger.error(speak_output)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        # Get the music section
        response = self.load_music_section()
        if response is not None:
            return response

        # Search for the artist
        try:
            artist_results = self.section.searchArtists(title=artist.value)
        except Exception as exception:
            speak_output = data[prompts.PMS_ARTIST_SEARCH_ERROR].format(artist.value)
            self.logger.error(exception)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        if len(artist_results) == 0:
            speak_output = data[prompts.PMS_ARTIST_SEARCH_EMPTY].format(artist.value)
            self.logger.error(speak_output)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        # Search for the song
        try:
            plex_track = artist_results[0].track(song.value)
        except NotFound  as exception:
            speak_output = data[prompts.PMS_SONG_SEARCH_ERROR].format(song=song.value, artist=artist.value)
            self.logger.error(exception)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response
        except Exception as exception:
            speak_output = data[prompts.PMS_SONG_SEARCH_ERROR].format(song=song.value, artist=artist.value)
            self.logger.error(exception)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        self.clear_playlist()
        self.add_plex_track(plex_track)

        playlist_name = data[prompts.PMS_PLNAME_SONG].format(song=song.value, artist=artist.value)
        self.set_playlist_name(playlist_name)
        speak_output = data[prompts.PMS_PLAYING].format(playlist_name)

        self.handler_input.response_builder.speak(speak_output)
        self.logger.info(speak_output)
        return self.start_playback()


    def play_album_by_artist (self) -> Response:
        """
        Play a specific album by a given artist.
        This method searches the specific album. If no tracks are found or an error
        occurs during the search, an appropriate response is returned. Otherwise,
        it clears the current playlist, adds the found tracks to the playlist, sets
        the playlist name, and starts playback.
        Returns:
            Response: The response object containing the result of the playback action.
        """

        self.logger.debug('In play_album_by_artist()')

        # get localization data
        data = self.handler_input.attributes_manager.request_attributes["_"]

        # Get variable(s) from intent
        artist = get_slot_value_v2(self.handler_input, 'artist')
        album = get_slot_value_v2(self.handler_input, 'album')
        if artist is None or album is None:
            speak_output = data[prompts.SKILL_INTENT_SLOTS_MISSING]
            self.logger.error(speak_output)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        # Get the music section
        response = self.load_music_section()
        if response is not None:
            return response

        # Search for the artist
        try:
            artist_results = self.section.searchArtists(title=artist.value)
        except Exception as exception:
            speak_output = data[prompts.PMS_ARTIST_SEARCH_ERROR].format(artist.value)
            self.logger.error(exception)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        if len(artist_results) == 0:
            speak_output = data[prompts.PMS_ARTIST_SEARCH_EMPTY].format(artist.value)
            self.logger.error(speak_output)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        # Search for the album
        try:
            plex_track_list = artist_results[0].album(album.value)
        except NotFound  as exception:
            speak_output = data[prompts.PMS_ALBUM_SEARCH_EMPTY].format(album=album.value, artist=artist.value)
            self.logger.error(exception)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response
        except Exception as exception:
            speak_output = data[prompts.PMS_ALBUM_SEARCH_ERROR].format(album.value, artist=artist.value)
            self.logger.error(exception)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        self.clear_playlist()
        self.add_plex_tracks(plex_track_list)

        playlist_name = data[prompts.PMS_PLNAME_ALBUM].format(album=album.value, artist=artist.value)
        self.set_playlist_name(playlist_name)
        speak_output = data[prompts.PMS_PLAYING].format(playlist_name)

        self.handler_input.response_builder.speak(speak_output)
        self.logger.info(speak_output)
        return self.start_playback()


    def play_music_by_genre (self) -> Response:
        """
        Play music by a given genre.
        This method searches music by genre. If no tracks are found or an error
        occurs during the search, an appropriate response is returned. Otherwise,
        it clears the current playlist, adds the found tracks to the playlist, sets
        the playlist name, and starts playback.
        Returns:
            Response: The response object containing the result of the playback action.
        """

        self.logger.debug('In play_music_by_genre()')

        # get localization data
        data = self.handler_input.attributes_manager.request_attributes["_"]

        # Get variable(s) from intent
        genre = get_slot_value_v2(self.handler_input, 'genre')
        if genre is None:
            speak_output = data[prompts.SKILL_INTENT_SLOTS_MISSING]
            self.logger.error(speak_output)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        # Get the music section
        response = self.load_music_section()
        if response is not None:
            return response

        # Search for the style (Plex server is more specfic with style than genre tags)
        try:
            plex_track_list = self.section.searchTracks(sort='random', maxresults=config.PMS_DEFAULT_MAX_RESULTS, style=genre.value)
        except Exception as exception:
            speak_output = data[prompts.PMS_GENRE_SEARCH_ERROR].format(genre.value)
            self.logger.error(exception)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        if len(plex_track_list)==0:
            speak_output = data[prompts.PMS_GENRE_SEARCH_EMPTY].format(genre.value)
            self.logger.error(speak_output)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        self.clear_playlist()
        self.add_plex_tracks(plex_track_list)

        playlist_name = data[prompts.PMS_PLNAME_MUSIC_BY_GENRE].format(genre.value)
        self.set_playlist_name(playlist_name)
        speak_output = data[prompts.PMS_PLAYING].format(playlist_name)

        self.handler_input.response_builder.speak(speak_output)
        self.logger.info(speak_output)
        return self.start_playback()


    def play_playlist (self) -> Response:
        """
        Play a plex playlist.
        This method searches for a specific playlist. If no playlist is found or an error
        occurs during the search, an appropriate response is returned. Otherwise,
        it clears the current playlist, adds the found tracks to the playlist, sets
        the playlist name, and starts playback.
        Returns:
            Response: The response object containing the result of the playback action.
        """

        self.logger.debug('In play_playlist()')

        # get localization data
        data = self.handler_input.attributes_manager.request_attributes["_"]

        # Get variable(s) from intent
        playlist = get_slot_value_v2(self.handler_input, 'playlist')
        if playlist is None:
            speak_output = data[prompts.SKILL_INTENT_SLOTS_MISSING]
            self.logger.error(speak_output)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        # Get the music section
        response = self.load_music_section()
        if response is not None:
            return response

        # Search for the playlist
        try:
            plex_track_list =  self.section.playlist(title=playlist.value)
        except NotFound  as exception:
            speak_output = data[prompts.PMS_PLAYLIST_SEARCH_EMPTY].format(playlist.value)
            self.logger.error(exception)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response
        except Exception as exception:
            speak_output = data[prompts.PMS_PLAYLIST_SEARCH_ERROR].format(playlist.value)
            self.logger.error(exception)
            return self.handler_input.response_builder.speak(speak_output).ask(speak_output).response

        self.clear_playlist()
        self.add_plex_tracks(plex_track_list)

        playlist_name = data[prompts.PMS_PLNAME_PLAYLIST].format(playlist.value)
        self.set_playlist_name(playlist_name)
        speak_output = data[prompts.PMS_PLAYING].format(playlist_name)

        self.handler_input.response_builder.speak(speak_output)
        self.logger.info(speak_output)
        return self.start_playback()