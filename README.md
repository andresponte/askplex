# AskPlex

AskPlex is an Alexa skill that allows you to play music hosted by your Plex Media Server (PMS).

> ***Disclaimer:*** AskPlex does not provide any media content or sources. Users must provide their own content from a Plex Media Server. The AskPlex project does not support bootleg content or other illegally sourced material.

## How to Install AskPlex

You will need to comply with the prerequisites below before creating the skill.

### Prerequisites

1.  Plex Media Server with your music library.
2.  Audio files must be in MP3 format with bit rates between 16 - 384 kB/s.
3.  DDNS service for your network (e.g., Duck DNS + IP update client).
4.  Internet service and router must be able to open and forward port **443**.
5.  A reverse proxy between your router and Plex Media Server, so that it can be accessed via **HTTPS** on port **443**.
6.  The reverse proxy must present a **valid and trusted SSL certificate**. Self-signed certificates are not allowed.
7.  Your Plex HTTPS URL must be accessible from the Echo devices network. If they are on the same network as the Plex server, your router must support NAT loopback.
8.  An Amazon user account (must be the same as the one used in the Alexa app and on Echo devices).

### Installation

1.  Sign in to [https://developer.amazon.com/](https://developer.amazon.com/) with your Amazon user account.
2.  Go to the Alexa Developer Console at [https://developer.amazon.com/alexa/console/ask](https://developer.amazon.com/alexa/console/ask) and then create the skill.
3.  Enter a name for your skill (e.g., AskPlex) and select your primary locale. (English (US) and Spanish (US) are currently supported. For additional locales support, feel free to create a custom interaction model at `interactionModels` folder, update the `lambda\askplex\language_strings.json` file and make a pull request).
4.  Choose the "Music & Audio" experience type, a custom model, and Alexa-hosted (Python) service. Select the hosting region closest to your location to reduce latency.
5.  In the "Templates" tab, click on "Import skill" and enter the AskPlex repository URL: (https://github.com/andresponte/askplex.git).
6.  Wait until the installation finishes, then go to the CUSTOM menu and open Invocations -> Skill Invocation Name.
7.  Set an invocation name for the skill (i.e. **plex server**).
8.  Click on "Build skill". This will take some time.
9.  Open the Code tab and edit the file "Skill Code/lambda/askplex/config.py".
10. Set the `PMS_SERVER_URL`, `PMS_SERVER_TOKEN`, and `PMS_DEFAULT_SECTION_NAME`. You can get your access token by following [these instructions](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/). For this step, please use a private browsing window to get a new access token; otherwise the AskPlex session will be closed when you end the session in your browser.
11. Click on 'Save' and then 'Build skill'. This will take some time.
12. When the deployment finishes, you can go to the Test tab.
13. Select Skill testing is enabled in Development.
14. Now you can type "open plex server".
15. If everything goes well, you should hear the reply: "Welcome to AskPlex. What would you like to do?"
16. Type: play music.
17. If the music starts playing, congratulations! AskPlex is now ready.

### Playlists Configuration

1.  Go to the Developer Console for the skill and open Assets -> Slot Types -> playlist_names.
2.  Enter the exact name of your Plex playlists.
3.  Click on "Save" and then "Build skill". Wait until the build finishes.

### How to Use AskPlex

1.  One-step voice command examples:
    - Alexa, ask plex server to play music
    - Alexa, ask plex server to play music by Moonspell
    - Alexa, ask plex server to play Full Moon Madness by Moonspell
    - Alexa, ask plex server to play the album Irreligious by Moonspell
    - Alexa, ask plex server to play the metal music
    - Alexa, ask plex server to play the playlist Recently Added
2.  Two-step voice commands examples:
    - Alexa, open plex server
        - *Welcome to AskPlex. What would you like to do?*
            - play music by Moonspell
    - Alexa, open plex server
        - *Welcome to AskPlex, you were listening to music by Moonspell. Would you like to resume?*
            - yes
3.  Invocation name is not needed for playback control:
    - Alexa, pause
    - Alexa, stop
    - Alexa, resume
    - Alexa, next
    - Alexa, previous
    - Alexa, shuffle on
    - Alexa, shuffle off
    - Alexa, loop on
    - Alexa, loop off