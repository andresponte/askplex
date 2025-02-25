import logging
import sys
import json
import os
import boto3

from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractRequestInterceptor, AbstractResponseInterceptor, AbstractExceptionHandler
from ask_sdk_model.interfaces.audioplayer import PlayerActivity
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_core.skill_builder import CustomSkillBuilder

from ask_sdk_model import Response
from ask_sdk_dynamodb.adapter import DynamoDbAdapter

from askplex import config
from askplex import prompts
from askplex import controller


# Setup Logging
logger = logging.getLogger(__name__)
logger.setLevel(config.SKILL_LOG_LEVEL)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(config.SKILL_LOG_LEVEL)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

# Defining the database region, table name and dynamodb persistence adapter
ddb_region = os.environ.get('DYNAMODB_PERSISTENCE_REGION')
ddb_table_name = os.environ.get('DYNAMODB_PERSISTENCE_TABLE_NAME')
ddb_resource = boto3.resource('dynamodb', region_name=ddb_region)
dynamodb_adapter = DynamoDbAdapter(table_name=ddb_table_name, create_table=False, dynamodb_resource=ddb_resource)

DYNAMODB_SCHEMA = 0

logger.info('Starting AskPlex...')


#
# Handler Classes
#
class CheckAudioInterfaceHandler(AbstractRequestHandler):
    """
    Check if device supports audio play.
    This can be used as the first handler to be checked, before invoking
    other handlers, thus making the skill respond to unsupported devices
    without doing much processing.
    Returns:
        Response: The response object with the spoken output for unsupported devices.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        if handler_input.request_envelope.context.system.device:
            # Since skill events won't have device information
            return handler_input.request_envelope.context.system.device.supported_interfaces.audio_player is None
        else:
            return False

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In CheckAudioInterfaceHandler()')

        # get localization data
        data = handler_input.attributes_manager.request_attributes["_"]

        speak_output = data[prompts.SKILL_DEVICE_NOT_SUPPORTED]
        logger.info(speak_output)

        handler_input.response_builder.speak(speak_output).set_should_end_session(True)
        return handler_input.response_builder.response


class SessionEndedRequestHandler(AbstractRequestHandler):
    """
    Handler for the session ended request.
    Returns:
        Response: The response object with no output speech.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In SessionEndedRequestHandler()")
        logger.info("Session ended with reason: {}".format(handler_input.request_envelope.request.reason))
        return handler_input.response_builder.response


class LaunchRequestHandler(AbstractRequestHandler):
    """
    Handler for a launch request" and "AMAZON.NavigateHomeIntent" intent.
    This method checks if the audioplayer is currently playing a track provided
    by this skill. If so, it replies with the current track details. Otherwise, it will
    check if there is a previous playback session and ask the used for resuming.
    Returns:
        Response: The response object with the spoken current track information
        if it is already playing music, a question for resuming the playback of
        previous session, or the welcome message.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (
            is_request_type('LaunchRequest')(handler_input) or
            is_intent_name('AMAZON.NavigateHomeIntent')(handler_input)
        )

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In LaunchRequestHandler()')
        persistence_attr = handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")
        player_controller = controller.Controller(logger, handler_input)

        # Check if there is a previous playback currently playing
        if playback_info.get("in_playback_session"):
            current_track = player_controller.get_current_track()
            if current_track is not None:
                player_activity = handler_input.request_envelope.context.audio_player.player_activity
                player_token = handler_input.request_envelope.context.audio_player.token
                current_track_id = current_track.get("id")

                if player_activity == PlayerActivity.PLAYING and player_token == current_track_id:
                    return player_controller.retrieve_track_details()

        # get localization data
        data = handler_input.attributes_manager.request_attributes["_"]

        persistence_attr = handler_input.attributes_manager.persistent_attributes
        session_attr = handler_input.attributes_manager.session_attributes
        playback_info = persistence_attr.get("playback_info")

        if not playback_info.get('in_playback_session'):
            speak_output = data[prompts.SKILL_WELCOME]
            reprompt = data[prompts.SKILL_WELCOME_REPROMPT]
            session_attr["request"]="action"
        else:
            speak_output = data[prompts.SKILL_WELCOME_PLAYBACK].format(playback_info.get('playlist_name'))
            reprompt = data[prompts.SKILL_WELCOME_PLAYBACK_REPROMPT]
            session_attr["request"]="resume"

        logger.info(speak_output)

        handler_input.response_builder.speak(speak_output).ask(reprompt)
        return handler_input.response_builder.response


class YesHandler(AbstractRequestHandler):
    """
    Handler for the 'AMAZON.YesIntent' intent.
    This method answers the question "Would you like to resume?", so it
    resumes the playback.
    Returns:
        Response: The response object with the play directive and the current track
        in audio item format. If there is no current track, the response object is empty.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('AMAZON.YesIntent')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In YesHandler()')
        session_attr = handler_input.attributes_manager.session_attributes

        if session_attr.get("request") == "resume":
            player_controller = controller.Controller(logger, handler_input)
            return player_controller.resume_playback()

        return handler_input.response_builder.response


class NoHandler(AbstractRequestHandler):
    """
    Handler for the 'AMAZON.NoIntent' intent.
    This method answers the question "Would you like to resume?", so it
    ask the user for the next action.
    Returns:
        Response: The response object containing the spoken question for the next action.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('AMAZON.NoIntent')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In NoHandler()')
        session_attr = handler_input.attributes_manager.session_attributes

        if session_attr.get("request") == "resume":
            # get localization data
            data = handler_input.attributes_manager.request_attributes["_"]
            persistence_attr = handler_input.attributes_manager.persistent_attributes
            playback_info = persistence_attr.get("playback_info")

            player_controller = controller.Controller(logger, handler_input)
            player_controller.clear_playlist()
            playback_info["in_playback_session"] = False

            session_attr["request"]="action"
            speak_output = data[prompts.SKILL_WELCOME_REPROMPT]
            handler_input.response_builder.speak(speak_output).ask(speak_output)

        return handler_input.response_builder.response


class HelpIntentHandler(AbstractRequestHandler):
    """
    Handler for the 'AMAZON.HelpIntent' intent.
    This method provides a help message to the user.
    Returns:
        Response: The response object containing the spoken help message.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('AMAZON.HelpIntent')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In HelpIntentHandler()')

        # get localization data
        data = handler_input.attributes_manager.request_attributes["_"]

        speak_output = data[prompts.SKILL_HELP]
        logger.info(speak_output)

        handler_input.response_builder.speak(speak_output).set_should_end_session(True)
        return handler_input.response_builder.response


#
# AudioPlayer Handlers
#
class ResumePlaybackHandler(AbstractRequestHandler):
    """
    Handler for the 'AMAZON.ResumeIntent' intent and PlayCommand from player controls,
    such as a button on a device, a remote control, or tap controls on an Alexa-enabled
    device with a screen
    Returns:
        Response: The response object with the play directive and the current track
        in audio item format. If there are no more tracks, the response object is empty.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name('AMAZON.ResumeIntent')(handler_input) or
                is_request_type('PlaybackController.PlayCommandIssued')(handler_input))

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In ResumePlaybackHandler()')
        persistence_attr = handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        if playback_info.get("in_playback_session"):
            player_controller = controller.Controller(logger, handler_input)
            return player_controller.resume_playback()


class StartOverPlaybackHandler(AbstractRequestHandler):
    """
    Handler for the 'AMAZON.StartOverIntent' intent.
    Returns:
        Response: The response object with the play directive and the current track
        in audio item format. If there are no more tracks, the response object is empty.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('AMAZON.StartOverIntent')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In StartOverPlaybackHandler()')
        persistence_attr = handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        if playback_info.get("in_playback_session"):
            player_controller = controller.Controller(logger, handler_input)
            return player_controller.start_playback()


class PausePlaybackHandler(AbstractRequestHandler):
    """
    Handler for the 'AMAZON.StopIntent', 'AMAZON.CancelIntent' or 'AMAZON.PauseIntent' intents
    and PlayCommand from player controls, such as a button on a device, a remote control, or
    tap controls on an Alexa-enabled device with a screen
    Returns:
        Response: The response object with the stop directive.
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        # type: (HandlerInput) -> bool
        return (is_intent_name('AMAZON.StopIntent')(handler_input) or
                is_intent_name('AMAZON.CancelIntent')(handler_input) or
                is_intent_name('AMAZON.PauseIntent')(handler_input) or
                is_request_type('PlaybackController.PauseCommandIssued')(handler_input))

    def handle(self, handler_input: HandlerInput) -> Response:
        # type: (HandlerInput) -> Response
        logger.debug('In PausePlaybackHandler()')
        persistence_attr = handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        if playback_info.get("in_playback_session"):
            player_controller = controller.Controller(logger, handler_input)
            return player_controller.pause_playback()

        return handler_input.response_builder.response


class PreviousPlaybackHandler(AbstractRequestHandler):
    """
    Handler for the 'AMAZON.PreviousIntent' intent and PreviousCommand from player controls,
    such as a button on a device, a remote control, or tap controls on an Alexa-enabled
    device with a screen
    Returns:
        Response: The response object with the play directive and the previous track
        in audio item format. If there are no more tracks, the response object is empty.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name('AMAZON.PreviousIntent')(handler_input) or
                is_request_type('PlaybackController.PreviousCommandIssued')(handler_input))

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In PreviousPlaybackHandler()')
        persistence_attr = handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        if playback_info.get("in_playback_session"):
            player_controller = controller.Controller(logger, handler_input)
            return player_controller.previous_playback()

        return handler_input.response_builder.response


class NextPlaybackHandler(AbstractRequestHandler):
    """
    Handler for the 'AMAZON.NextIntent' intent and NextCommand from player controls,
    such as a button on a device, a remote control, or tap controls on an Alexa-enabled
    device with a screen
    Returns:
        Response: The response object with the play directive and the next track
        in audio item format. If there are no more tracks, the response object is empty.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name('AMAZON.NextIntent')(handler_input) or
                is_request_type('PlaybackController.NextCommandIssued')(handler_input))

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In NextPlaybackHandler()')
        persistence_attr = handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        if playback_info.get("in_playback_session"):
            player_controller = controller.Controller(logger, handler_input)
            return player_controller.next_playback()

        return handler_input.response_builder.response


class ShuffleOnPlaybackHandler(AbstractRequestHandler):
    """
    Handler for the 'AMAZON.ShuffleOnIntent' intent.
    Returns:
        Response: The response object with no output speech.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('AMAZON.ShuffleOnIntent')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In ShuffleOnPlaybackHandler()')
        persistence_attr = handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        if playback_info.get("in_playback_session"):
            player_controller = controller.Controller(logger, handler_input)
            return player_controller.shuffle_playback(True)

        return handler_input.response_builder.response


class ShuffleOffPlaybackHandler(AbstractRequestHandler):
    """
    Handler for the 'AMAZON.ShuffleOffIntent' intent.
    Returns:
        Response: The response object with no output speech.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('AMAZON.ShuffleOffIntent')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In ShuffleOffPlaybackHandler()')
        persistence_attr = handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        if playback_info.get("in_playback_session"):
            player_controller = controller.Controller(logger, handler_input)
            return player_controller.shuffle_playback(False)

        return handler_input.response_builder.response


class LoopOnPlaybackHandler(AbstractRequestHandler):
    """
    Handler for the 'AMAZON.LoopOnIntent' intent.
    Returns:
        Response: The response object with no output speech.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('AMAZON.LoopOnIntent')(handler_input)
    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In LoopOnPlaybackHandler()')
        persistence_attr = handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        if playback_info.get("in_playback_session"):
            player_controller = controller.Controller(logger, handler_input)
            return player_controller.loop_playback(True)

        return handler_input.response_builder.response


class LoopOffPlaybackHandler(AbstractRequestHandler):
    """
    Handler for the 'AMAZON.LoopOffIntent' intent.
    Returns:
        Response: The response object with no output speech.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('AMAZON.LoopOffIntent')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In LoopOffPlaybackHandler()')
        persistence_attr = handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        if playback_info.get("in_playback_session"):
            player_controller = controller.Controller(logger, handler_input)
            return player_controller.loop_playback(False)

        return handler_input.response_builder.response


class PlaybackStartedHandler(AbstractRequestHandler):
    """
    Handler for the 'PlaybackStarted' event.
    Returns:
        Response: The response object with no output speech.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_request_type('AudioPlayer.PlaybackStarted')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In PlaybackStartedHandler()')
        player_controller = controller.Controller(logger, handler_input)
        return player_controller.playback_started()


class PlaybackStoppedHandler(AbstractRequestHandler):
    """
    Handler for the 'PlaybackStopped' event.
    Returns:
        Response: The response object with no output speech.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_request_type('AudioPlayer.PlaybackStopped')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        # type: (HandlerInput) -> Response
        logger.debug('In PlaybackStoppedHandler()')
        player_controller = controller.Controller(logger, handler_input)
        return player_controller.playback_stopped()


class PlaybackNearlyFinishedHandler(AbstractRequestHandler):
    """
    Handler for the 'PlaybackNearlyFinished' event.
    Returns:
        Response: The response object with the enqueue directive and the next track
        in audio item format. If there are no more tracks, the response object is empty.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_request_type('AudioPlayer.PlaybackNearlyFinished')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In PlaybackNearlyFinishedHandler()')
        player_controller = controller.Controller(logger, handler_input)
        return player_controller.playback_nearly_finished()


class PlaybackFinishedHandler(AbstractRequestHandler):
    """
    Handler for the 'PlaybackFinished' event.
    Returns:
        Response: The response object with no output speech.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_request_type('AudioPlayer.PlaybackFinished')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In PlaybackFinishedHandler()')
        player_controller = controller.Controller(logger, handler_input)
        return player_controller.playback_finished()


class PlaybackFailedEventHandler(AbstractRequestHandler):
    """
    Handler for the 'PlaybackFailed' event.
    Returns:
        Response: The response object with no output speech.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_request_type('AudioPlayer.PlaybackFailed')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In PlaybackFailedEventHandler()')
        player_controller = controller.Controller(logger, handler_input)
        return player_controller.playback_failed()


#
# Custom Intents
#
class PlaybackSongDetailsHandler(AbstractRequestHandler):
    """
    Handler for the 'PlaybackSongDetails' intent.
    Returns:
        Response: The response object containing the spoken output with the track details.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('PlaybackSongDetails')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In PlaybackSongDetailsHandler()')
        persistence_attr = handler_input.attributes_manager.persistent_attributes
        playback_info = persistence_attr.get("playback_info")

        if playback_info.get("in_playback_session"):
            player_controller = controller.Controller(logger, handler_input)
            current_track = player_controller.get_current_track()

            if current_track is not None:
                player_activity = handler_input.request_envelope.context.audio_player.player_activity
                player_token = handler_input.request_envelope.context.audio_player.token
                current_track_id = current_track.get("id")

                if player_activity == PlayerActivity.PLAYING and player_token == current_track_id:
                    return player_controller.retrieve_track_details()

        return handler_input.response_builder.response


class PlayRandomMusicHandler(AbstractRequestHandler):
    """
    Handler for the 'PlayRandomMusic' intent.
    Returns:
        Response: The response object containing the result of the playback action.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('PlayRandomMusic')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In PlayRandomMusicHandler()')
        player_controller = controller.Controller(logger, handler_input)
        return player_controller.play_random_music()


class PlayMusicByArtistHandler(AbstractRequestHandler):
    """
    Handler for the 'PlayMusicByArtist' intent.
    Returns:
        Response: The response object containing the result of the playback action.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('PlayMusicByArtist')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In PlayMusicByArtistHandler()')
        player_controller = controller.Controller(logger, handler_input)
        return player_controller.play_music_by_artist()


class PlaySongByArtistHandler(AbstractRequestHandler):
    """
    Handler for the 'PlaySongByArtist' intent.
    Returns:
        Response: The response object containing the result of the playback action.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('PlaySongByArtist')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In PlaySongByArtistHandler()')
        player_controller = controller.Controller(logger, handler_input)
        return player_controller.play_song_by_artist()


class PlayAlbumByArtistHandler(AbstractRequestHandler):
    """
    Handler for the 'PlayAlbumByArtist' intent.
    Returns:
        Response: The response object containing the result of the playback action.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('PlayAlbumByArtist')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In PlayAlbumByArtistHandler()')
        player_controller = controller.Controller(logger, handler_input)
        return player_controller.play_album_by_artist()


class PlayMusicByGenreHandler(AbstractRequestHandler):
    """
    Handler for the 'PlayMusicByGenre' intent.
    Returns:
        Response: The response object containing the result of the playback action.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('PlayMusicByGenre')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In PlayMusicByGenreHandler()')
        player_controller = controller.Controller(logger, handler_input)
        return player_controller.play_music_by_genre()


class PlayPlaylistHandler(AbstractRequestHandler):
    """
    Handler for the 'PlayPlaylist' intent.
    Returns:
        Response: The response object containing the result of the playback action.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name('PlayPlaylist')(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.debug('In PlayPlaylistHandler()')
        player_controller = controller.Controller(logger, handler_input)
        return player_controller.play_playlist()


#
# Exception Handers
#
class CatchAllExceptionHandler(AbstractExceptionHandler):
    """
    Handler for the exceptions.
    Returns:
        None.
    """

    def can_handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> bool
        return True

    def handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> Response
        logger.info("In CatchAllExceptionHandler()")
        logger.error(exception, exc_info=True)

        # get localization data
        data = handler_input.attributes_manager.request_attributes["_"]

        speak_output = data[prompts.SKILL_EXCEPTION]
        handler_input.response_builder.speak(speak_output).ask(speak_output).set_should_end_session(True)

        return handler_input.response_builder.response


#
# Request Interceptors
#
class LocalizationInterceptor(AbstractRequestInterceptor):
    """
    Interceptor for loading the locale specific data.
    Returns:
        None.
    """

    def process(self, handler_input):
        locale = handler_input.request_envelope.request.locale
        logger.info("Locale is: {}".format(locale[:2]))

        # localized strings stored in language_strings.json
        with open("askplex/language_strings.json") as language_prompts:
            language_data = json.load(language_prompts)
        # set default translation data to broader translation

        data = language_data[locale[:2]]
        # if a more specialized translation exists, then select it instead
        # example: "fr-CA" will pick "fr" translations first, but if "fr-CA" translation exists,
        #          then pick that instead
        if locale in language_data:
            data.update(language_data[locale])
        handler_input.attributes_manager.request_attributes["_"] = data


class RequestLogger(AbstractRequestInterceptor):
    """
    Interceptor for logging the alexa requests.
    Returns:
        None.
    """

    def process(self, handler_input):
        # type: (HandlerInput) -> None
        logger.debug("Alexa Request: {}".format(
            handler_input.request_envelope.request))


class LoadPersistenceAttributesRequestInterceptor(AbstractRequestInterceptor):
    """
    Interceptor for checking the database schema and loading default data if needed.
    Returns:
        None.
    """

    def process(self, handler_input):
        # type: (HandlerInput) -> None
        persistence_attr = handler_input.attributes_manager.persistent_attributes

        if len(persistence_attr) == 0:
            defaults = True
        else:
            schema = persistence_attr.get("schema")
            if schema is None:
                defaults = True
            else:
                if int(schema) == DYNAMODB_SCHEMA:
                    defaults = False
                else:
                    defaults = True

        if defaults:
            # Set the default values
            persistence_attr["schema"] = DYNAMODB_SCHEMA
            persistence_attr["pms_settings"] = {
                "max_results": config.PMS_DEFAULT_MAX_RESULTS,
                "section_name": config.PMS_DEFAULT_SECTION_NAME
            }
            persistence_attr["playback_setting"] = {
                "loop": False,
                "shuffle": False
            }
            persistence_attr["playback_info"] = {
                "playlist": {},
                "playlist_name": "",
                "play_order": [],
                "index": 0,
                "offset_in_ms": 0,
                "playback_index_changed": False,
                "next_stream_enqueued": False,
                "in_playback_session": False,
            }
            logger.debug(f"Controller's default settings loaded")


class ResponseLogger(AbstractResponseInterceptor):
    """
    Interceptor for logging the alexa responses.
    Returns:
        None.
    """

    def process(self, handler_input, response):
        # type: (HandlerInput, Response) -> None
        logger.debug("Alexa Response: {}".format(response))


class SavePersistenceAttributesResponseInterceptor(AbstractResponseInterceptor):
    """
    Interceptor for saving the persistance data to the database.
    Returns:
        None.
    """

    def process(self, handler_input, response):
        # type: (HandlerInput, Response) -> None
        handler_input.attributes_manager.save_persistent_attributes()


# Create custom skill
sb = CustomSkillBuilder(persistence_adapter = dynamodb_adapter)
# Register Intent Handlers
sb.add_request_handler(CheckAudioInterfaceHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(YesHandler())
sb.add_request_handler(NoHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(ResumePlaybackHandler())
sb.add_request_handler(StartOverPlaybackHandler())
sb.add_request_handler(PausePlaybackHandler())
sb.add_request_handler(PreviousPlaybackHandler())
sb.add_request_handler(NextPlaybackHandler())
sb.add_request_handler(ShuffleOnPlaybackHandler())
sb.add_request_handler(ShuffleOffPlaybackHandler())
sb.add_request_handler(LoopOnPlaybackHandler())
sb.add_request_handler(LoopOffPlaybackHandler())
sb.add_request_handler(PlaybackStartedHandler())
sb.add_request_handler(PlaybackStoppedHandler())
sb.add_request_handler(PlaybackNearlyFinishedHandler())
sb.add_request_handler(PlaybackFinishedHandler())
sb.add_request_handler(PlaybackFailedEventHandler())
sb.add_request_handler(PlaybackSongDetailsHandler())
sb.add_request_handler(PlayRandomMusicHandler())
sb.add_request_handler(PlayMusicByArtistHandler())
sb.add_request_handler(PlayAlbumByArtistHandler())
sb.add_request_handler(PlaySongByArtistHandler())
sb.add_request_handler(PlayMusicByGenreHandler())
sb.add_request_handler(PlayPlaylistHandler())
sb.add_exception_handler(CatchAllExceptionHandler())
# Register Interceptors
sb.add_global_request_interceptor(LocalizationInterceptor())
sb.add_global_request_interceptor(RequestLogger())
sb.add_global_request_interceptor(LoadPersistenceAttributesRequestInterceptor())
sb.add_global_response_interceptor(ResponseLogger())
sb.add_global_response_interceptor(SavePersistenceAttributesResponseInterceptor())


lambda_handler = sb.lambda_handler()
logger.info('AskPlex Ready!')