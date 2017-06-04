#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import time
import random

from .account import spin_pokestop_request, get_inventory_items
from .utils import in_radius

log = logging.getLogger(__name__)

ITEMS = {
    0: 'unknown',
    1: 'PokeBall',
    2: 'Great Ball',
    3: 'Ultra Ball',
    4: 'Master Ball',
    101: 'Potion',
    102: 'Super Potion',
    103: 'Hyper Potion',
    104: 'Max Potion',
    201: 'Revive',
    202: 'Max Revive',
    701: 'Razz Berry',
    702: 'Bluk Berry',
    703: 'Nanab Berry',
    704: 'Wepar Berry',
    705: 'Pinap Berry',
    1101: 'Sun Stone',
    1102: 'Kings Rock',
    1103: 'Metal Coat',
    1104: 'Dragon Scale',
    1105: 'Upgrade'
}


# Check if Pokestop is spinnable and not on cooldown.
def pokestop_spinnable(fort, step_location):
    spinning_radius = 0.04
    in_range = in_radius((fort['latitude'], fort['longitude']), step_location,
                         spinning_radius)
    now = time.time()
    pause_needed = 'cooldown_complete_timestamp_ms' in fort and fort[
        'cooldown_complete_timestamp_ms'] / 1000 > now
    return in_range and not pause_needed


# 50% Chance to spin a Pokestop.
def spinning_try(api, fort, step_location, account):
    # Set 50% Chance to spin a Pokestop.
    if random.randint(0, 100) < 50:
        time.sleep(random.uniform(0.8, 1.8))  # Do not let Niantic throttle.
        spin_response = spin_pokestop_request(api, fort, step_location)
        if not spin_response:
            return False

        # Check for reCaptcha
        captcha_url = spin_response['responses']['CHECK_CHALLENGE'][
            'challenge_url']
        if len(captcha_url) > 1:
            log.debug('Account encountered a reCaptcha.')
            return False

        # Catch all possible responses.
        spin_result = spin_response['responses']['FORT_SEARCH']['result']
        if spin_result is 1:
            time.sleep(random.uniform(2, 4))  # Do not let Niantic throttle.
            items_recieved = spin_response['responses']['FORT_SEARCH'][
                'items_awarded']
            log.info('Successful Pokestop spin with %s.', account['username'])
            log.debug('Recieved %s from Pokestop %s.', items_recieved,
                      fort['id'])
            return True
        # Catch all other results.
        elif spin_result is 2:
            log.info('Pokestop %s was not in range to spin for account %s',
                     fort['id'], account['username'])
        elif spin_result is 3:
            log.info('Failed to spin Pokestop %s. %s Has recently spun this' +
                     'stop.', fort['id'], account['username'])
        elif spin_result is 4:
            log.info('Failed to spin Pokestop %s. %s Inventory is full.',
                     fort['id'], account['username'])
        elif spin_result is 5:
            log.info('Account %s has spun maximum Pokestops for today.',
                     account['username'])
        else:
            log.info('Failed to spin a Pokestop with account %s .' +
                     'Unknown result %d.', account['username'], spin_result)
    return False


def clear_inventory(api, account, map_dict):
    inventory_items = get_inventory_items(map_dict)
    clear_responses = []
    for item in inventory_items:
        if 'item_id' and 'count' in item:
            item_id = item['item_id']
            count = item['count']
            # Keep 5 Items in Inventory
            total_items = item.get('count', 0)
            items_to_drop = total_items - 5
            if item_id in ITEMS:
                item_name = ITEMS[item_id]
                # Do not let Niantic throttle
                time.sleep(random.uniform(1.75, 2.75))
                clear_inventory_response = clear_inventory_request(
                    api, item_id, items_to_drop)

                captcha_url = clear_inventory_response['responses'][
                    'CHECK_CHALLENGE']['challenge_url']
                if len(captcha_url) > 1:
                    log.info('Account encountered a reCaptcha.')
                    return False

                clear_response = clear_inventory_response[
                    'responses']['RECYCLE_INVENTORY_ITEM']
                clear_responses.append(clear_response)

                clear_result = clear_response['result']
                if clear_result is 1:
                    log.info('Clearing %s %ss succeeded.', count, item_name)
                elif clear_result is 2:
                    log.debug('Not enough items to clear, parsing failed.')
                elif clear_result is 3:
                    log.debug('Tried to recycle incubator, parsing failed.')
                else:
                    log.warning('Failed to clear inventory.')

                log.debug('Recycled inventory: \n\r{}'.format(clear_responses))

    return clear_responses


def clear_inventory_request(api, item_id, items_to_drop):
    try:
        req = api.create_request()
        req.recycle_inventory_item(item_id=item_id, count=items_to_drop)
        req.check_challenge()
        req.get_hatched_eggs()
        req.get_inventory()
        req.check_awarded_badges()
        req.get_buddy_walked()
        clear_inventory_response = req.call()

        return clear_inventory_response

    except Exception as e:
        log.warning('Exception while clearing Inventory: %s', repr(e))
        return False
