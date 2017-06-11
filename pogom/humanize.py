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
def spinning_try(api, fort, step_location, account, map_dict):
    # Set 50% Chance to spin a Pokestop.
    if random.randint(0, 100) < 50:
        time.sleep(random.uniform(2, 4))  # Do not let Niantic throttle.
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
            log.info('Clearing Inventory...')
            clear_inventory(api, account, map_dict)
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
            if total_items > random.randint(5, 10):
                # Do not let Niantic throttle
                time.sleep(random.uniform(2, 4))
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


def egg_check(api, account, map_dict):
    incubator = {}
    basic_incubator_empty = False
    needs_egg = None
    ready_to_hatch = None
    usedIncubatorCount = 0

    inventory = map_dict['responses'][
        'GET_INVENTORY']['inventory_delta']['inventory_items']
    for item in inventory:
        inventory_item_data = item['inventory_item_data']
        if 'pokemon_data' in inventory_item_data:
            pokemon_data = inventory_item_data['pokemon_data']
            egg_id = pokemon_data['id']
            if ('is egg'and'egg_km_walked_target' in pokemon_data):
                egg_type = pokemon_data['egg_km_walked_target']
                log.debug('Account %s has the following Eggs in' +
                          ' Inventory: %s km.', account['username'],
                          egg_type)
    # for item in inventory:
    #    inventory_item_data = item['inventory_item_data']
        if 'egg_incubators' in inventory_item_data:
            incubators = inventory_item_data['egg_incubators']
            count = -1
            for incubator in incubators:
                basic_incubator = inventory_item_data[
                        'egg_incubators']['egg_incubator'][count]['item_id']
                count += 1
                if 'pokemon_id' in inventory_item_data[
                        'egg_incubators']['egg_incubator'][count]:
                    log.debug(
                        'Basic Incubator in use already!')
                    usedIncubatorCount += 1
                    basic_incubator_empty = False
                else:
                    if incubator == 901:
                        needs_egg = inventory_item_data[
                            'egg_incubators']['egg_incubator'][count]['id']
                        log.debug('Basic Incubator is free using it on' +
                                  'Account: %s', account['username'])
                        basic_incubator_empty = True
                    else:
                        ready_to_hatch = inventory_item_data[
                            'egg_incubators']['egg_incubator'][count]['id']
                        log.debug(
                            'Egg is going to hatch, clicking it!')
                        basic_incubator_empty = True
                        if (ready_to_hatch is not None and egg_id is not None
                                or needs_egg is not None and egg_id
                                is not None):
                            if ready_to_hatch is None:
                                basic_incubator = needs_egg
                            else:
                                basic_incubator = ready_to_hatch
                            while (basic_incubator_empty is True and
                                    pokemon_data[
                                        'egg_km_walked_target'] == 2.0):
                                time.sleep(random.uniform(2, 4))
                                egg_hatching_response = egg_hatching_request(
                                    api, egg_id, basic_incubator)

                                captcha_url = egg_hatching_response[
                                    'responses']['CHECK_CHALLENGE'][
                                        'challenge_url']
                                if len(captcha_url) > 1:
                                    log.info(
                                        'Account encountered a reCaptcha.')
                                    return False
                                egg_response = egg_hatching_response[
                                    'responses']['USE_ITEM_EGG_INCUBATOR']
                                egg_result = egg_response['result']
                                if egg_result is 0:
                                    log.exception(
                                        'Server responded with "unset"')
                                elif egg_result is 1:
                                    log.info(
                                        'Successfully used Basic Incubator')
                                    ready_to_hatch = None
                                    needs_egg = None
                                    basic_incubator_empty = False
                                    break
                                elif egg_result is 2:
                                    log.exception(
                                        'Incubator %s not found!', incubator)
                                elif egg_result is 3:
                                    log.exception(
                                        'Egg not found! Egg: %s', egg_id)
                                elif egg_result is 4:
                                    log.exception(
                                        'Given ID does not point to EGG!')
                                elif egg_result is 5:
                                    log.exception('Incubator in use!')
                                elif egg_result is 6:
                                    log.exception('Egg already incubating!')
                                elif egg_result is 7:
                                    log.exception('Egg Hatching Failure: %s',
                                                  egg_result)


def egg_hatching_request(api, egg_id, basic_incubator):
    try:
        req = api.create_request()
        req.use_item_egg_incubator(item_id=basic_incubator,
                                   pokemon_id=egg_id)
        req.check_challenge()
        req.get_hatched_eggs()
        req.get_inventory()
        req.check_awarded_badges()
        req.get_buddy_walked()
        egg_hatching_request = req.call()

        return egg_hatching_request

    except Exception as e:
        log.warning('Exception while hatching egg: %s', repr(e))
        return False
