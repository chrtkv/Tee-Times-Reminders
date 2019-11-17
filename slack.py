import requests
import logging
import re
import json
from requests_toolbelt.multipart.encoder import MultipartEncoder
import time
import urllib.parse

logging.captureWarnings(True)


def get_crumb(url):
    # get the login form for crumb parsing
    headers = {
        'user-agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36",
    }
    # get login form text
    form_text = requests.get(url, headers=headers).text
    # search crumb
    crumb_string = re.search("name=\"crumb\" value=\"(.*?)\">", form_text)[1]
    # urlencode it
    crumb = urllib.parse.quote(crumb_string)
    return crumb


CONFIG = json.loads(open('config.json', 'rt').read())['slack']
USER = CONFIG['email']
PASSWORD = CONFIG['password']
MAIN_URL = CONFIG['url']

CRUMB = get_crumb(MAIN_URL)


def get_cookie(crumb=CRUMB, user=USER, password=PASSWORD):
    url = "https://thisisix.slack.com"

    payload = "signin=1&crumb={}&email={}&password={}".format(crumb, user, password)
    headers = {
        'authority': "thisisix.slack.com",
        'content-type': "application/x-www-form-urlencoded",
        'user-agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36"
    }

    response = requests.post(url, data=payload, headers=headers, allow_redirects=False)

    for i in re.split(' ', response.headers['Set-Cookie']):
        if "d=" in i:
            return i


cookie = get_cookie()


def get_info():
    '''
    Returns token, company id, user id, company url, etc.
    '''
    url = "https://app.slack.com/auth?app=client"

    headers = {
        'cookie': cookie
    }

    auth = requests.get(url, headers=headers)
    auth_data = re.search('stringify\((.*)\);\n', auth.text).group(1)
    auth_data_json = json.loads(auth_data)
    teams = auth_data_json['teams']
    for team in teams:
        team_info = teams[team]
    return team_info


info = get_info()
token = info['token']
COMPANY_ID = info['id']


CHANNEL = 'DKU1X4KJ5'


TO_DELETE = [
    "I’m sorry! I can’t find that reminder. Maybe it was deleted?",
    "OK! I’ve deleted the reminder about.",
    "marked the reminder about",
    "archived the channel",
    "^~.*",
    "You have been removed",
    "OK! I’ll remind you about",
    "Ok! I’ll remind you about"
]


def get_conversations_list(company_id=COMPANY_ID):
    url = "{}/api/client.counts".format(MAIN_URL)

    multipart_data = MultipartEncoder(
        fields={
            'thread_counts_by_channel': 'true',
            'token': token,
        }
    )

    headers = {
        "Content-Type": multipart_data.content_type,
        'cookie': cookie
    }

    conversations = requests.post(url, data=multipart_data, headers=headers)

    return conversations.json()


def get_channel_info(channel_id):
    url = "{}/api/groups.info".format(MAIN_URL)

    multipart_data = MultipartEncoder(
        fields={
            'channel': channel_id,
            'no_user_profile': 'true',
            'token': token,
        }
    )

    headers = {
        "Content-Type": multipart_data.content_type,
        'cookie': cookie
    }

    r = requests.post(url, data=multipart_data, headers=headers)

    print(r.content)

    channel_info = r.json()['channel']

    return channel_info


def get_test():
    url = "{}/api/client.boot".format(MAIN_URL)

    multipart_data = MultipartEncoder(
        fields={
            'token': token,
        }
    )

    headers = {
        "Content-Type": multipart_data.content_type,
        'cookie': cookie
    }

    r = requests.post(url, data=multipart_data, headers=headers)

    channels_info = r.json()['channels']

    return channels_info


def print_all_channels(company_id=COMPANY_ID):
    types = {
        'channels': 'channels',
        'threads': 'threads',
        'personal': 'ims',
        'group': 'mpims'
    }
    channels = get_test()
    # for conversation in get_conversations_list(company_id)[types[type_of_channel]]:
    #     # print(conversation['id'])
    #     channel_name = get_test()['name']
    #     print(conversation['id'], ": ", channel_name)
    for channel in channels:
        print(channel['id'], channel['name'])


def slackbot_id():
    for conversation in get_conversations_list()['ims']:
        print(get_channel_info(conversation['id']))

        if 'slackbot' in get_channel_info(conversation['id'])['name']:
            return conversation['id']


def get_messages(channel_id):
    url = "{}/api/conversations.history".format(MAIN_URL)

    multipart_data = MultipartEncoder(
        fields={
            'channel': channel_id,
            'limit': '1000',
            'token': token,
        }
    )

    headers = {
        "Content-Type": multipart_data.content_type,
        'cookie': cookie
    }

    get_msgs = requests.post(url, data=multipart_data, headers=headers, verify=False)
    messages = get_msgs.json()["messages"]

    return messages


def delete_message(timestamp, channel=CHANNEL):
    url = '{}/api/chat.delete'.format(MAIN_URL)

    multipart_data = MultipartEncoder(
        fields={
            'channel': channel,
            'ts': timestamp,
            'token': token
        }
    )

    headers = {
        "Content-Type": multipart_data.content_type,
        'cookie': cookie
    }

    delete = requests.post(url, data=multipart_data, headers=headers)
    print(delete.json())


def delete_list(messages):
    delete_list = []
    for message in messages:
        for string in TO_DELETE:
            if re.search(string, message['text']):
                delete_list.append(message['ts'])
        if (time.time() - float(message['ts'])) > 2592000:
            delete_list.append(message['ts'])

    return delete_list


def send_message(text, channel_id):
    url = "{}/api/chat.postMessage".format(MAIN_URL)
    
    multipart_data = MultipartEncoder(
        fields={
            'channel': channel_id,
            'text': text,
            'token': token,
        }
    )

    headers = {
        "Content-Type": multipart_data.content_type,
        'cookie': cookie
    }

    send_msgs = requests.post(url, data=multipart_data, headers=headers, verify=False)
    print(send_msgs.content)


def set_reminder(text, channel_id):
    url = "{}/api/chat.command".format(MAIN_URL)
    
    multipart_data = MultipartEncoder(
        fields={
            'command': '/remind',
            'channel': channel_id,
            'text': text,
            'token': token,
        }
    )

    headers = {
        "Content-Type": multipart_data.content_type,
        'cookie': cookie
    }

    set_reminder = requests.post(url, data=multipart_data, headers=headers, verify=False)
    print(set_reminder.content)


if __name__ == "__main__":
    send_message('fffff', 'DKZTSJNLU')
    # print(slackbot_id())
    # print(get_channel_info('CP12JBT4Y'))
    # for i in get_messages(CHANNEL):
    #     time.sleep(2)
    #     delete_message(i['ts'])
    # for i in delete_list(get_messages(CHANNEL)):
    #     time.sleep(2)
    #     delete_message(i)
    # print(time.time())
