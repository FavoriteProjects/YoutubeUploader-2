import argparse
import http.client
import httplib2
import os
import random
import time
import configparser
import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

UPLOAD_DIRECTORY = None
youtube = None
UPLOAD_DESCRIPTION = None
UPLOAD_PRIVACY = None

httplib2.RETRIES = 1
# Maximum number of times to retry before giving up.
MAX_RETRIES = 10
# Always retry when these exceptions are raised.
RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError, http.client.NotConnected,
                        http.client.IncompleteRead, http.client.ImproperConnectionState,
                        http.client.CannotSendRequest, http.client.CannotSendHeader,
                        http.client.ResponseNotReady, http.client.BadStatusLine)
# Always retry when an apiclient.errors.HttpError with one of these status
# codes is raised.
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
CLIENT_SECRETS_FILE = 'client_secret.json'
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'
VALID_PRIVACY_STATUSES = ('public', 'private', 'unlisted')

# CALL THIS METHOD ONCE BEFORE CALLING UPLOADALL()
def init():
    global UPLOAD_DIRECTORY
    global UPLOAD_DESCRIPTION
    global UPLOAD_PRIVACY
    global MAX_RETRIES
    global youtube

    # Set values from config.ini
    config = configparser.ConfigParser()
    config.read("config.ini")
    UPLOAD_DIRECTORY = config["Upload"]["directory"]
    UPLOAD_DESCRIPTION = config["Upload"]["description"]
    UPLOAD_PRIVACY = config["Upload"]["privacy"]
    MAX_RETRIES = int(config["Upload"]["maxRetries"])

     # Create image directory if it doesnt exist
    if not os.path.exists(UPLOAD_DIRECTORY):
        os.makedirs(UPLOAD_DIRECTORY)
    
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, SCOPES)
    credentials = flow.run_console()
    youtube = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)

# CALL THIS METHOD TO UPLOAD ALL FILES IN THE UPLOAD FOLDER
def uploadAll():
        # Generate the list of files to upload
    files = []
    for (dirpath, dirnames, filenames) in os.walk(UPLOAD_DIRECTORY):
        files.extend(filenames)
        break

    os.chdir(UPLOAD_DIRECTORY)
    for curFile in files:
        print("Now uploading: " + curFile)
        args = argparse.Namespace(file=curFile,
                         title=curFile,
                         description=UPLOAD_DESCRIPTION,
                         category=22,
                         keywords="",
                         privacyStatus=UPLOAD_PRIVACY)

        try:
            initialize_upload(youtube, args)
        except HttpError as e:
            print('An HTTP error %d occurred:\n%s' %
                  (e.resp.status, e.content))
    os.chdir("..")


def initialize_upload(youtube, options):
    tags = None
    if options.keywords:
        tags = options.keywords.split(',')

    body = dict(
        snippet=dict(
            title=options.title,
            description=options.description,
            tags=tags,
            categoryId=options.category
        ),
        status=dict(
            privacyStatus=options.privacyStatus
        )
    )

    # Call the API's videos.insert method to create and upload the video.
    insert_request = youtube.videos().insert(
        part=','.join(list(body.keys())),
        body=body,
        media_body=MediaFileUpload(options.file, chunksize=-1, resumable=True)
    )

    resumable_upload(insert_request)

# This method implements an exponential backoff strategy to resume a
# failed upload.
def resumable_upload(request):
    response = None
    error = None
    retry = 0
    while response is None:
        try:
            print('Uploading file...')
            status, response = request.next_chunk()
            if response is not None:
                if 'id' in response:
                    print(('Video https://www.youtube.com/watch?v=%s was successfully uploaded.' %
                           response['id']))
                else:
                    exit('The upload failed with an unexpected response: %s' % response)
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                error = 'A retriable HTTP error %d occurred:\n%s' % (e.resp.status,
                                                                     e.content)
            else:
                raise
        except RETRIABLE_EXCEPTIONS as e:
            error = 'A retriable error occurred: %s' % e

        if error is not None:
            print(error)
            retry += 1
            if retry > MAX_RETRIES:
                exit('No longer attempting to retry.')

            max_sleep = 2 ** retry
            sleep_seconds = random.random() * max_sleep
            print('Sleeping %f seconds and then retrying...' % sleep_seconds)
            time.sleep(sleep_seconds)


if __name__ == '__main__':
    init()
    uploadAll()
