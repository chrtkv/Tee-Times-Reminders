#!/usr/bin/env python3

"""
Module for generating list of tournaments with Moscow time for remind
"""
from slack import send_message, set_reminder
import json
import time
from datetime import datetime, timedelta

import requests
from lxml import etree

from pytz import timezone
import re

with open("config.json") as config_json:
    CONFIG = json.load(config_json)

slack_group = CONFIG['slack']['group']

def get_live_trnms_list():
    """
    Return all live tournaments as list of dictionaries with tour_code and trnm_id.
    Example: {'tour_code': 'R', 'trnm_id': '521'}
    """

    live_trnms_list = []
    xml_tree = etree.parse(CONFIG['feed']['trigger'])
    xml_root = xml_tree.getroot()

    for trnm in xml_root.iter("feed"):
        # if trnm.get('event_id') == '1':
        if trnm.get('live') == 'yes':
            tour_code = trnm.get('tourcode')
            trnm_id = trnm.get('perm_id')
            live_trnms_list.append({'tour_code': tour_code, 'trnm_id': trnm_id})

    def compare_values(tour_letter):
        if tour_letter == 'R':
            return 1
        elif tour_letter == 'S':
            return 2
        elif tour_letter == 'H':
            return 3
        elif tour_letter == 'C':
            return 4
        elif tour_letter == 'M':
            return 5

    return sorted(live_trnms_list, key=lambda x: compare_values(x['tour_code']))


def get_json(url):
    """
    Returns json as dict
    """
    request_result = requests.get(url)
    if(request_result.status_code == 200):
        return request_result.json()
    elif(request_result.status_code == 404):
        return 404


def get_reminder(trnm_info):
    # TODO: Divide function.
    # Each feed should parse separately to its own dict.
    # This function will get values for generating and return string.
    """
    Generates reminder string from template
    """
    reminder = {}

    tour_code = trnm_info['tour_code']
    trnm_id = trnm_info['trnm_id']
    reminder_message_template = "*{} tour* - {} - Round {}. Spotheck starts at *{} MSK*. Play starts at *{} MSK*."
    reminder_reminder_template = "#ix-team-tcss \"{}\" {}"

    feed_url = CONFIG['feed']['tee_times'].format(tour_code.lower(), trnm_id)
    tee_times_json = get_json(feed_url)
    if tee_times_json == 404:
        return "Teetimes feed not found for {}{} ({})".format(tour_code, trnm_id, feed_url)

    tee_times_tournament = tee_times_json.get("tournament")
    tee_times_rounds = tee_times_tournament.get("rounds")

    trnm_name = tee_times_tournament['TournamentName']
    current_round = int(tee_times_tournament.get("CurrentRound"))
    courses = tee_times_rounds[current_round - 1]["courses"]
    round_state = tee_times_rounds[current_round - 1]["RoundState"]

    segments = [i["segments"] for i in courses]

    groups = []
    start_times_list = []

    for i in segments:
        for b in i:
            for c in b["groups"]:  # this is real groups
                groups.append(c)
                start_times_list.append(c["StartTime"])  # contains list of start times

    month = int(groups[0]["StartDate"][:2])
    day = int(groups[0]["StartDate"][3:5])
    year = int(groups[0]["StartDate"][6:10])

    schedule_json = get_json(CONFIG['feed']['schedule'])
    current_year_for_tour = schedule_json.get("currentYears")[tour_code.lower()]
    schedule_years = schedule_json.get("years")

    for i in schedule_years:
        if i['year'] == current_year_for_tour:
            schedule_current_year_tours = i['tours']

    for i in schedule_current_year_tours:
        if i["tourCodeLc"] == tour_code.lower():
            schedule_current_year_trns = i["trns"]

    for i in schedule_current_year_trns:
        if i["permNum"] == trnm_id:
            time_zone = i["timeZone"]

    local_timezone = timezone(time_zone)
    time_format = "%I:%M %p"
    time_hours = [time.strptime(t, time_format) for t in start_times_list]
    time_start_sorted = [time.strftime("%-I", h) for h in sorted(time_hours)]  # here is sorted list of starting times for each group

    start_hour = int(time_start_sorted[0])
    # round_state = "Suspended"
    # search resume time from the message
    if round_state == "Suspended":
        message_json = get_json(CONFIG['feed']['message'].format(tour_code.lower(), trnm_id))
        message = message_json.get('notes')[0]['html']
        # message = "<div class=\"generatedMssg\">Round 1 delayed due to inclement weather</div>"
        if re.search(' at ([0-9]):', message):
            haveResumeTime = True
            start_hour = int(re.search(' at ([0-9]):', message)[1])
        else:
            haveResumeTime = False

    local_time = local_timezone.localize(datetime(year, month, day, start_hour))  # local trnm time
    moscow_time = local_time.astimezone(timezone('Europe/Moscow'))
    play_time = moscow_time.strftime("%H:%M")
    spotcheck_time = (moscow_time - timedelta(minutes=60)).strftime("%H:%M")
    reminder_time = (moscow_time - timedelta(minutes=75)).strftime("%H:%M")

    if local_time.date() == datetime.today().date():
        reminder_message = reminder_message_template.format(tour_code.upper(), trnm_name, current_round, spotcheck_time, play_time)
    elif local_time.date() < datetime.today().date():
        if round_state == "Suspended":
            if haveResumeTime:
                resume_message = "{}. {}. Will resume at {}:00 MSK".format(current_round, round_state, play_time)
                reminder_message = reminder_message_template.format(tour_code.upper(), trnm_name, resume_message, spotcheck_time, play_time)
            else:
                resume_message = "{}. {}. There is no information about resume time. Check it manually".format(current_round, round_state)
                reminder_message = "*{} Tour* - {} - Round {}".format(tour_code.upper(), trnm_name, resume_message)
        else:
            reminder = reminder_message_template.format(tour_code.upper(), trnm_name, current_round, "started {}. It\'s {} now".format(local_time.date(), round_state), "*")
    # elif local_time.date() > datetime.today().date():
    #     reminder = reminder_template.format(tour_code.upper(), trnm_name, current_round, "will start {}".format(local_time.date()), "*")
    reminder_reminder = reminder_reminder_template.format(reminder_message, reminder_time)
    reminder['message'] = reminder_message
    reminder['reminder'] = reminder_reminder

    return reminder


def create_message():
    remind_message = []
    if get_live_trnms_list():
        for each_trnm in get_live_trnms_list():
            if get_reminder(each_trnm):
                message = get_reminder(each_trnm)['message']
                remind_message.append(message)
            # remind_message.append(get_reminder_string(each_trnm))
        return remind_message
    else:
        return


def create_reminders():
    # print("Here is reminders for Slack:")
    # reminder_format = "#ix-team-tcss \"{}\" {}"
    reminders = []
    # remind_time = ''
    # i = 1
    for each_trnm in get_live_trnms_list():
        # if 'Suspended' in get_reminder_string(each_trnm):
        #     remind_time = '13:00'
        # else:
        # remind_time = get_reminder(each_trnm)[-10:-5]

        # if re.match(r'[0-9]|[0-2][0-9]:[0-5][0-9]', remind_time):
        reminder = get_reminder(each_trnm)['reminder']
        reminders.append(reminder)
        # i += 1
    return reminders


if __name__ == '__main__':
    # print(get_live_trnms_list())
    print(create_message())
    print(create_reminders())
    for message in create_message():
        if (message):
            send_message(message, slack_group)

    for i in create_reminders():
        set_reminder(i, slack_group)
    # for each_trnm in get_live_trnms_list():
    # print(get_reminder_string(each_trnm))

"""
TODO: rewrite part for suspended if the message haven't
resume time
"""
