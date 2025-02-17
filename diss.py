# Sample simulator demo
# Miguel Matos - miguel.marques.matos@tecnico.ulisboa.pt
# (c) 2012-2018

import ast
import csv
import gc
from operator import itemgetter

import datetime
import time
from collections import defaultdict
import random
import sys
import os

import yaml
import pickle
import logging
import numpy
from sim import sim
import utils
from sortedList import SortedCollection

# Messages structures
BLOCK_ID, BLOCK_PARENT_ID, BLOCK_HEIGHT, BLOCK_TIMESTAMP, BLOCK_GEN_NODE, BLOCK_TX, BLOCK_RECEIVED_TS \
    = 0, 1, 2, 3, 4, 5, 6

INV_TYPE, INV_CONTENT_ID = 0, 1

HEADER_ID, HEADER_PARENT_ID = 0, 1

# Node structure
CURRENT_CYCLE, NODE_CURRENT_BLOCK, NODE_INV, NODE_PARTIAL_BLOCKS, NODE_MEMPOOL, NODE_BLOCKS_ALREADY_REQUESTED, \
NODE_TX_ALREADY_REQUESTED, NODE_TIME_TO_GEN, NODE_NEIGHBOURHOOD, NODE_NEIGHBOURHOOD_INV, NODE_NEIGHBOURHOOD_STATS, MSGS, \
NODE_HEADERS_TO_REQUEST, NODE_TIME_TO_SEND, NODE_TX_TIMER, NODES_SIZE, MY_UNCONFIRMED_TX, MY_CONFIRMED_TX, HAD_TO_INC, TIME_SINCE_LAST_DEC, TIME_SINCE_LAST_INC, DEPTH \
    = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21

NODE_INV_RECEIVED_BLOCKS, NODE_INV_RECEIVED_TX = 0, 1

NEIGHBOURHOOD_KNOWN_BLOCKS, NEIGHBOURHOOD_KNOWN_TX, NEIGHBOURHOOD_TX_TO_SEND = 0, 1, 2

TOP_N_NODES, STATS = 0, 1

STATS_T, STATS_T_1 = 0, 1

TOTAL_TLL, TOTAL_MSG_RECEIVED = 0, 1

TOP, RAND = 0, 1

# Counter structure
INV_MSG, GETHEADERS_MSG, HEADERS_MSG, GETDATA_MSG, BLOCK_MSG, CMPCTBLOCK_MSG, GETBLOCKTXN_MSG, BLOCKTXN_MSG, TX_MSG, MISSING_TX, \
ALL_INVS = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10

BLOCK_TYPE, TX_TYPE = True, False

RECEIVED_INV, RELEVANT_INV, RECEIVED_GETDATA = 0, 1, 2

MINE, NOT_MINE = True, False

SENT, RECEIVED = 0, 1

RECEIVE_TX, RECEIVED_BLOCKTX = 0, 1

INV_BLOCK_ID, INV_BLOCK_TTL = 0, 1

TIME, INBOUND = 0, 1

TIME_COMMITTED, COMMITTED = 0, 1

TS_RECEIVED, TTL = 0, 1

TX_T_CYCLE_RECEIVED, TX_T_CYCLE_COMMITTED = 0, 1

NOT_SAMPLED, TIMER_T, TIMER_T_1 = 0, 1, 2

TOTAL_TIME, TOTAL_SENT = 0, 1

CONF_TIME_COMMITTED, CONF_TIME_IT_TOOK = 0, 1

HTI_BOOL, HTI_TIME = 0, 1

TIME_TO_REM_TX_FROM_CONFIRMED = 1 * 60 * 60

HTI_RESET_TIME = 4 * 60 * 60

TIME_TO_WAIT_BEFORE_DEC = 2 * 60 * 60

# Time frame between t and t_1
TIME_FRAME = 14400

# Sample intervals we take to calculate the time weight
SAMPLE_SIZE = 100

ALPHA = 0.3

# Weight we give to blocks received from a nodes
BLOCK_WEIGHT = 100

# Weight we give to time it takes for  tx to appear in a block once we send it
TX_TIME_WEIGHT = 0.2

# Time it should take for a tx to be accepted
TIME_FOR_TX_CONFIRMATION = 30 * 60

# Interval where the log is not recorded first x sec and last x sec
INTERVAL = 5 * 3600


def init():
    # schedule execution for all nodes
    for nodeId in nodeState:
        sim.schedulleExecution(CYCLE, nodeId)

    # other things such as periodic measurements can also be scheduled
    # to schedule periodic measurements use the following
    # for c in range(nbCycles * 10):
    #    sim.scheduleExecutionFixed(MEASURE_X, nodeCycle * (c + 1))


def improve_performance(cycle):
    if cycle % 600 != 0 or cycle == 0:
        return

    for i in range(len(blocks_created)):
        if blocks_created[i][BLOCK_HEIGHT] + 2 < highest_block and not isinstance(blocks_created[i][BLOCK_TX], int):
            for tx in blocks_created[i][BLOCK_TX]:
                for myself in range(nb_nodes):
                    if tx in nodeState[myself][NODE_INV][NODE_INV_RECEIVED_TX]:
                        del nodeState[myself][NODE_INV][NODE_INV_RECEIVED_TX][tx]
                    if tx in nodeState[myself][NODE_MEMPOOL]:
                        del nodeState[myself][NODE_MEMPOOL][tx]

                    for neighbour in nodeState[myself][NODE_NEIGHBOURHOOD]:
                        if tx in nodeState[myself][NODE_NEIGHBOURHOOD_INV][neighbour][NEIGHBOURHOOD_KNOWN_TX]:
                            del nodeState[myself][NODE_NEIGHBOURHOOD_INV][neighbour][NEIGHBOURHOOD_KNOWN_TX][tx]
                        if tx in nodeState[myself][NODE_NEIGHBOURHOOD_INV][neighbour][NEIGHBOURHOOD_TX_TO_SEND]:
                            del nodeState[myself][NODE_NEIGHBOURHOOD_INV][neighbour][NEIGHBOURHOOD_TX_TO_SEND][tx]

            replace_block = list(blocks_created[i])
            tx_list = replace_block[BLOCK_TX]
            replace_block[BLOCK_TX] = len(replace_block[BLOCK_TX])
            blocks_created[i] = tuple(replace_block)
            del replace_block
            del tx_list
    gc.collect()
    if gc.garbage:
        gc.garbage[0].set_next(None)
        del gc.garbage[:]


def get_headers_to_send(myself, target, new_block):
    current_block = get_block(myself, new_block[BLOCK_PARENT_ID])
    headers_to_send = [get_block_header(new_block)]
    while not check_availability(myself, target, BLOCK_TYPE, current_block[BLOCK_ID]):
        headers_to_send = [get_block_header(current_block)] + headers_to_send
        current_block = get_block(myself, current_block[BLOCK_PARENT_ID])

    return headers_to_send


def CYCLE(myself):
    global nodeState, blocks_mined_by_randoms, miners

    # with churn the node might be gone
    if myself not in nodeState:
        return

    # Change miners during simulation simulation
#    if myself == 0 and nodeState[myself][CURRENT_CYCLE] == 61200:
#        miners = random.sample(range(nb_nodes), 5)
#        for i in range(0, 2):
#            miners.pop()
#        nodes_to_append = random.sample(range(nb_nodes), 2)
#        while nodes_to_append in miners:
#            nodes_to_append = random.sample(range(nb_nodes), 2)
#        for node in nodes_to_append:
#           miners.append(node)

    if nodeState[myself][CURRENT_CYCLE] % 600 == 0 and hop_based_broadcast:
        increase_relay(myself)

    if hop_based_broadcast and nodeState[myself][CURRENT_CYCLE] == 1800:
        size = len(nodeState[myself][NODE_NEIGHBOURHOOD]) // 2
        nodeState[myself][NODES_SIZE] = [size, size]

    # show progress for one node
    if myself == 0 and nodeState[myself][CURRENT_CYCLE] % 600 == 0:
        improve_performance(nodeState[myself][CURRENT_CYCLE])
        value = datetime.datetime.fromtimestamp(time.time())
        #output.write('{} run: {} cycle: {} mempool size: {}\n'.format(value.strftime('%Y-%m-%d %H:%M:%S'), runId,  nodeState[myself][CURRENT_CYCLE], len(nodeState[myself][NODE_MEMPOOL])))
        #output.flush()
        print('{} run: {} cycle: {} mempool size: {} Top {}'.format(value.strftime('%Y-%m-%d %H:%M:%S'), runId,  nodeState[myself][CURRENT_CYCLE], len(nodeState[myself][NODE_MEMPOOL]), nodeState[myself][NODES_SIZE][TOP]))

    # If a node can generate transactions
    i = 0
    n = get_nb_of_tx_to_gen(myself, nodeState[myself][CURRENT_CYCLE])
    while i < n:
        generate_new_tx(myself)
        i += 1

    # If the node can generate a block
    if nodeState[myself][NODE_TIME_TO_GEN] == -1:
        next_t_to_gen(myself)

    if nodeState[myself][NODE_TIME_TO_GEN] == nodeState[myself][CURRENT_CYCLE]:
        next_t_to_gen(myself)
        if myself in miners or (myself not in miners and random.random() < 0.01 and
                                blocks_mined_by_randoms < total_blocks_mined_by_randoms):
            if myself not in miners:
                blocks_mined_by_randoms += 1
            new_block = generate_new_block(myself)

            # Check if can send as compact or send through inv
            for target in nodeState[myself][NODE_NEIGHBOURHOOD]:
                if check_availability(myself, target, BLOCK_TYPE, new_block[BLOCK_PARENT_ID]):
                    sim.send(CMPCTBLOCK, target, myself, cmpctblock(new_block))
                    if should_log(myself):
                        nodeState[myself][MSGS][CMPCTBLOCK_MSG] += 1
                    update_neighbourhood_inv(myself, target, BLOCK_TYPE, new_block[BLOCK_ID])

                else:
                    msg_to_send = get_headers_to_send(myself, target, new_block)
                    sim.send(HEADERS, target, myself, msg_to_send)
                    if should_log(myself):
                        nodeState[myself][MSGS][INV_MSG][SENT] += 1
            del new_block

    # Send new transactions either created or received
    broadcast_invs(myself)

    nodeState[myself][CURRENT_CYCLE] += 1
    # schedule next execution
    if nodeState[myself][CURRENT_CYCLE] < nb_cycles:
        sim.schedulleExecution(CYCLE, myself)


def INV(myself, source, vInv):
    global nodeState

    new_connection(myself, source)

    ask_for = []
    headers_to_request = []
    tx_inv = False
    for inv in vInv:
        if inv[INV_TYPE] == TX_TYPE:
            if not tx_inv and should_log(myself):
                nodeState[myself][MSGS][INV_MSG][RECEIVED] += 1
                tx_inv = True
            ask_for += process_tx_inv(myself, source, inv)
        elif inv[INV_TYPE] == BLOCK_TYPE:
            headers_to_request += process_block_inv(myself, source, inv)
        else:
            raise ValueError('INV, else, node received invalid inv type. This condition is not coded')

    if ask_for:
        sim.send(GETDATA, source, myself, ask_for)
        if should_log(myself):
            nodeState[myself][MSGS][GETDATA_MSG][SENT] += 1
        del ask_for

    if headers_to_request:
        sim.send(GETHEADERS, source, myself, headers_to_request)
        if should_log(myself):
            nodeState[myself][MSGS][GETHEADERS_MSG] += 1
        del headers_to_request


def GETHEADERS(myself, source, get_headers):
    global nodeState

    headers_to_send = []
    for id in get_headers:
        block = get_block(myself, id)
        if block is not None:
            headers_to_send.append(get_block_header(block))
        else:
            raise ValueError('GETHEADERS, else, node received invalid headerID')

    sim.send(HEADERS, source, myself, headers_to_send)
    if should_log(myself):
        nodeState[myself][MSGS][HEADERS_MSG] += 1
    del headers_to_send


def HEADERS(myself, source, headers):
    global nodeState

    new_connection(myself, source)

    process_new_headers(myself, source, headers)
    data_to_request = get_data_to_request(myself, source)
    if len(data_to_request) <= 16:
        # If is a new block in the main chain try and direct fetch
        sim.send(GETDATA, source, myself, data_to_request)
        if should_log(myself):
            nodeState[myself][MSGS][GETDATA_MSG][SENT] += 1
        del data_to_request
    else:
        # Else rely on other means of download
        raise ValueError('HEADERS, else, this condition is not coded')


def GETDATA(myself, source, requesting_data):
    global nodeState

    is_tx = False
    for inv in requesting_data:
        if inv[INV_TYPE] == TX_TYPE:
            if not is_tx:
                if should_log(myself):
                    nodeState[myself][MSGS][GETDATA_MSG][RECEIVED] += 1
                is_tx = True

            if should_log(myself):
                nodeState[myself][MSGS][ALL_INVS][RECEIVED_GETDATA] += 1
            tx = get_transaction(myself, inv[INV_CONTENT_ID])
            if tx is not None:
                sim.send(TX, source, myself, tx)
                if should_log(myself):
                    nodeState[myself][MSGS][TX_MSG] += 1
                update_neighbourhood_inv(myself, source, TX_TYPE, tx)

        elif inv[INV_TYPE] == BLOCK_TYPE:
            block = get_block(myself, inv[INV_CONTENT_ID])
            if block is not None:
                sim.send(BLOCK, source, myself, block)
                if should_log(myself):
                    nodeState[myself][MSGS][BLOCK_MSG] += 1
                update_neighbourhood_inv(myself, source, BLOCK_TYPE, block[BLOCK_ID])
                del block
            else:
                raise ValueError('GETDATA, MSG_BLOCK else, this condition is not coded and shouldn\'t happen')

        else:
            raise ValueError('GETDATA, else, this condition is not coded and shouldn\'t happen')


def BLOCK(myself, source, block):
    global nodeState

    if block[BLOCK_ID] in nodeState[myself][NODE_BLOCKS_ALREADY_REQUESTED]:
        nodeState[myself][NODE_BLOCKS_ALREADY_REQUESTED].remove(block[BLOCK_ID])

    if block[BLOCK_ID] in nodeState[myself][NODE_HEADERS_TO_REQUEST]:
        nodeState[myself][NODE_HEADERS_TO_REQUEST].remove(block[BLOCK_ID])

    process_block(myself, source, block)


def CMPCTBLOCK(myself, source, cmpctblock):
    global nodeState

    new_connection(myself, source)

    in_mem_cmpctblock = get_cmpctblock(myself, cmpctblock[BLOCK_ID])
    if have_it(myself, BLOCK_TYPE, cmpctblock[BLOCK_ID]) or in_mem_cmpctblock:
        update_neighbour_statistics(myself, source)
        update_neighbourhood_inv(myself, source, BLOCK_TYPE, cmpctblock[BLOCK_ID])
        return

    in_headers = get_header(myself, cmpctblock[BLOCK_ID])
    if in_headers is not None:
        nodeState[myself][NODE_HEADERS_TO_REQUEST].remove(cmpctblock[BLOCK_ID])

    # Check if we have all tx
    tx_to_request = []
    for tx_id in cmpctblock[BLOCK_TX]:
        tx = get_transaction(myself, tx_id)
        if tx is None:
            tx_to_request.append(tx_id)

    if tx_to_request:
        sim.send(GETBLOCKTXN, source, myself, (cmpctblock[BLOCK_ID], tx_to_request))
        if should_log(myself):
            nodeState[myself][MSGS][GETBLOCKTXN_MSG] += 1
            nodeState[myself][MSGS][MISSING_TX] += len(tx_to_request)
        nodeState[myself][NODE_PARTIAL_BLOCKS].append(cmpctblock[BLOCK_ID])
        del tx_to_request
    else:
        process_block(myself, source, cmpctblock)


def GETBLOCKTXN(myself, source, tx_request):
    global nodeState

    sim.send(BLOCKTXN, source, myself, tx_request)
    if should_log(myself):
        nodeState[myself][MSGS][BLOCKTXN_MSG] += 1


def BLOCKTXN(myself, source, tx_requested):
    global nodeState

    if have_it(myself, BLOCK_TYPE, tx_requested[0]):
        return

    for tx in tx_requested[1]:
        if tx in nodeState[myself][NODE_TX_ALREADY_REQUESTED]:
            nodeState[myself][NODE_TX_ALREADY_REQUESTED].remove(tx)

    process_block(myself, source, build_cmpctblock(myself, tx_requested))


def TX(myself, source, tx):
    global nodeState

    if tx in nodeState[myself][NODE_TX_ALREADY_REQUESTED]:
        nodeState[myself][NODE_TX_ALREADY_REQUESTED].remove(tx)

    update_neighbourhood_inv(myself, source, TX_TYPE, tx)
    if not have_it(myself, TX_TYPE, tx):
        update_have_it(myself, TX_TYPE, tx)
        nodeState[myself][NODE_MEMPOOL][tx] = None
        if myself not in bad_nodes:
            push_to_send(myself, tx, NOT_MINE)
        if tx_array:
            tx_created[tx][RECEIVE_TX] += 1


# --------------------------------------
# Inv functions
def process_tx_inv(myself, source, inv):
    ask_for = []
    if should_log(myself):
        nodeState[myself][MSGS][ALL_INVS][RECEIVED_INV] += 1

    update_neighbourhood_inv(myself, source, TX_TYPE, inv[INV_CONTENT_ID])
    seen_tx = have_it(myself, TX_TYPE, inv[INV_CONTENT_ID])
    if not seen_tx and inv[INV_CONTENT_ID] not in nodeState[myself][NODE_TX_ALREADY_REQUESTED]:
        ask_for.append(inv)
        nodeState[myself][NODE_TX_ALREADY_REQUESTED].append(inv[INV_CONTENT_ID])
        if should_log(myself):
            nodeState[myself][MSGS][ALL_INVS][RELEVANT_INV] += 1

    return ask_for


def process_block_inv(myself, source, inv):
    headers_to_request = []
    update_neighbourhood_inv(myself, source, BLOCK_TYPE, inv[INV_CONTENT_ID])
    seen_block = have_it(myself, BLOCK_TYPE, inv[INV_CONTENT_ID])
    if not seen_block:
        if get_header(myself, inv[INV_CONTENT_ID]) is None:
            headers_to_request.append(inv[INV_CONTENT_ID])
    return headers_to_request


# --------------------------------------


# --------------------------------------
# Header functions
def process_new_headers(myself, source, headers):
    global nodeState

    for header in headers:
        seen_block = have_it(myself, BLOCK_TYPE, header[HEADER_ID])
        have_header = None
        if not seen_block:
            have_header = get_header(myself, header[HEADER_ID])

        seen_parent = have_it(myself, BLOCK_TYPE, header[HEADER_PARENT_ID])
        have_parent_header = None
        if not seen_parent:
            have_parent_header = get_header(myself, header[HEADER_PARENT_ID])

        update_neighbourhood_inv(myself, source, BLOCK_TYPE, header[HEADER_ID])
        update_neighbourhood_inv(myself, source, BLOCK_TYPE, header[HEADER_PARENT_ID])

        if (not seen_parent or have_parent_header is None) and header[HEADER_PARENT_ID] != -1:
            nodeState[myself][NODE_HEADERS_TO_REQUEST].append(header[HEADER_PARENT_ID])
            nodeState[myself][NODE_HEADERS_TO_REQUEST].append(header[HEADER_ID])
            # raise ValueError("process_new_headers Received a header with a parent that we don't have: {}"
            #                .format(header[HEADER_PARENT_ID]))

        elif (seen_parent or have_parent_header or header[HEADER_PARENT_ID] == -1) and (not seen_block and have_header is None):
            nodeState[myself][NODE_HEADERS_TO_REQUEST].append(header[HEADER_ID])

        else:
            raise ValueError("process_new_headers else condition reached help!: {}"
                             .format(header[HEADER_ID]))


def get_data_to_request(myself, source):
    global nodeState

    data_to_request = []
    for header_id in nodeState[myself][NODE_HEADERS_TO_REQUEST]:
        if check_availability(myself, source, BLOCK_TYPE, header_id) and \
                header_id not in nodeState[myself][NODE_BLOCKS_ALREADY_REQUESTED]:
            data_to_request.append((BLOCK_TYPE, header_id))
            nodeState[myself][NODE_BLOCKS_ALREADY_REQUESTED].append(header_id)

    return data_to_request


# --------------------------------------


# --------------------------------------
# Block related functions
def generate_new_block(myself):
    global nodeState, block_id, blocks_created, highest_block, tx_created_after_last_block

    # First block or
    # Not first block which means getting highest block to be the parent
    tx_to_include = get_tx_to_block(myself)
    if nodeState[myself][NODE_CURRENT_BLOCK] is None:
        new_block = (
            block_id, -1, 0, nodeState[myself][CURRENT_CYCLE], myself, tx_to_include, 0, nodeState[myself][CURRENT_CYCLE])
    else:
        local_highest_block = get_block(myself, nodeState[myself][NODE_CURRENT_BLOCK])
        new_block = (
            block_id, local_highest_block[BLOCK_ID], local_highest_block[BLOCK_HEIGHT] + 1, nodeState[myself][CURRENT_CYCLE],
            myself, tx_to_include, 0, nodeState[myself][CURRENT_CYCLE])

    # Store the new block
    blocks_created.append(new_block)
    nodeState[myself][NODE_INV][NODE_INV_RECEIVED_BLOCKS][new_block[BLOCK_ID]] = nodeState[myself][CURRENT_CYCLE]
    nodeState[myself][NODE_CURRENT_BLOCK] = new_block[BLOCK_ID]
    block_id += 1
    del tx_created_after_last_block
    tx_created_after_last_block = []
    if new_block[BLOCK_HEIGHT] > highest_block:
        highest_block = new_block[BLOCK_HEIGHT]
    return new_block


def get_block(myself, block_id):
    if not have_it(myself, BLOCK_TYPE, block_id):
        raise ValueError("get_block I don't have id: {}".format(block_id))

    for item in reversed(blocks_created):
        if item[0] == block_id:
            return item
    return None


def super_get_block(block_id):
    for item in reversed(blocks_created):
        if item[0] == block_id:
            return item
    return None


def get_tx_in_block(block, tx_id):
    if tx_id in block[BLOCK_TX]:
        return tx_id
    return None


def cmpctblock(block):
    cmpct_tx = []
    for tx in block[BLOCK_TX]:
        cmpct_tx.append(tx)
    return block[BLOCK_ID], block[BLOCK_PARENT_ID], block[BLOCK_HEIGHT], block[BLOCK_TIMESTAMP], block[BLOCK_GEN_NODE], cmpct_tx, \
           block[BLOCK_RECEIVED_TS]


def get_cmpctblock(myself, block_id):
    if block_id in nodeState[myself][NODE_PARTIAL_BLOCKS]:
        return True
    return False


def build_cmpctblock(myself, block_and_tx):
    cmpctblock = super_get_block(block_and_tx[0])

    if tx_array:
        for tx in block_and_tx[1]:
            tx_created[tx][RECEIVED_BLOCKTX] += 1

    nodeState[myself][NODE_PARTIAL_BLOCKS].remove(cmpctblock[BLOCK_ID])

    return cmpctblock


def get_block_header(block):
    return block[BLOCK_ID], block[BLOCK_PARENT_ID]


def process_block(myself, source, block):
    global nodeState
    # Check if it's a new block
    if not have_it(myself, BLOCK_TYPE, block[BLOCK_ID]):
        update_have_it(myself, BLOCK_TYPE, block[BLOCK_ID])
        if nodeState[myself][NODE_CURRENT_BLOCK] is None or \
                block[BLOCK_HEIGHT] > get_block(myself, nodeState[myself][NODE_CURRENT_BLOCK])[BLOCK_HEIGHT]:
            nodeState[myself][NODE_CURRENT_BLOCK] = block[BLOCK_ID]
        next_t_to_gen(myself)

        # Remove tx from MEMPOOL and from vINV_TX_TO_SEND
        update_tx(myself, block)

        # Broadcast new block
        update_neighbour_statistics(myself, source)
        update_neighbourhood_inv(myself, source, BLOCK_TYPE, block[BLOCK_ID])
        for target in nodeState[myself][NODE_NEIGHBOURHOOD]:
            if target == source or check_availability(myself, target, BLOCK_TYPE, block[BLOCK_ID]):
                continue
            elif check_availability(myself, target, BLOCK_TYPE, block[BLOCK_PARENT_ID]):
                sim.send(CMPCTBLOCK, target, myself, cmpctblock(block))
                if should_log(myself):
                    nodeState[myself][MSGS][CMPCTBLOCK_MSG] += 1
                update_neighbourhood_inv(myself, target, BLOCK_TYPE, block[BLOCK_ID])
            else:
                sim.send(HEADERS, target, myself, [get_block_header(block)])
                if should_log(myself):
                    nodeState[myself][MSGS][HEADERS_MSG] += 1

    else:
        update_neighbour_statistics(myself, source)
        update_neighbourhood_inv(myself, source, BLOCK_TYPE, block[BLOCK_ID])


# --------------------------------------


# --------------------------------------
# Algorithm related functions
def update_neighbour_statistics(myself, source):
    current_cycle = nodeState[myself][CURRENT_CYCLE]
    if nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source][STATS_T][TOTAL_TLL]:
        time_frame = current_cycle - nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source][STATS_T][TOTAL_TLL][-1][1]
    elif nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source][STATS_T_1][TOTAL_TLL]:
        time_frame = current_cycle - TIME_FRAME
    else:
        time_frame = current_cycle

    nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source][STATS_T][TOTAL_TLL].append([time_frame, current_cycle])
    nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source][STATS_T][TOTAL_MSG_RECEIVED] += 1
    stats_to_remove = []
    for stat in nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source][STATS_T][TOTAL_TLL]:
        if stat[1] + TIME_FRAME <= current_cycle:
            stats_to_remove.append(stat)
    for stat in stats_to_remove:
        nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source][STATS_T][TOTAL_TLL].remove(stat)
        nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source][STATS_T][TOTAL_MSG_RECEIVED] -= 1
        nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source][STATS_T_1][TOTAL_TLL] += stat[0]
        nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source][STATS_T_1][TOTAL_MSG_RECEIVED] += 1

    update_top(myself, source)


def get_classification(myself, source, current_cycle):
    t_blocks = []
    t_1_blocks = []
    for block in nodeState[myself][NODE_INV][NODE_INV_RECEIVED_BLOCKS].items():
        if block[1] + TIME_FRAME > current_cycle:
            t_blocks.append(block)
        else:
            t_1_blocks.append(block)

    if hop_based_broadcast and timer_solution:
        update_timer_lists(myself, source, current_cycle)

    t_k = 0
    t_n = nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source][STATS_T][TOTAL_MSG_RECEIVED]
    timer_k = 0
    timer_n = 0
    for tx in nodeState[myself][NODE_TX_TIMER][source][TIMER_T]:
        tx_struct = nodeState[myself][NODE_TX_TIMER][source][TIMER_T][tx]
        if tx_struct[TX_T_CYCLE_COMMITTED] is not None:
            timer_n += 1
            timer_k += tx_struct[TX_T_CYCLE_COMMITTED] - tx_struct[TX_T_CYCLE_RECEIVED]
    for stat in nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source][STATS_T][TOTAL_TLL]:
        t_k += stat[0]
    if t_n == 0:
        t = 0
    elif timer_k == 0:
        t = (t_k / t_n) + (len(t_blocks) - t_n)
    else:
        t = ((t_k / t_n)/600) + (len(t_blocks) - t_n) + ((timer_k / timer_n) / 600)

    t_1_k = nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source][STATS_T_1][TOTAL_TLL]
    t_1_n = nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source][STATS_T_1][TOTAL_MSG_RECEIVED]
    timer_1_k = nodeState[myself][NODE_TX_TIMER][source][TIMER_T_1][TOTAL_TIME]
    timer_1_n = nodeState[myself][NODE_TX_TIMER][source][TIMER_T_1][TOTAL_SENT]
    if t_1_n == 0:
        t_1 = 0
    elif timer_1_k == 0:
        t_1 = ((t_1_k / t_1_n)/600) + (len(t_1_blocks) - t_1_n)
    else:
        t_1 = ((t_1_k / t_1_n)/600) + (len(t_1_blocks) - t_1_n) + ((timer_1_k / timer_1_n) / 600)

    return (1 - ALPHA) * t_1 + ALPHA * t


def update_top(myself, source):
    if source in nodeState[myself][NODE_NEIGHBOURHOOD_STATS][TOP_N_NODES]:
        return

    up_top(myself)


def up_top(myself):
    scores = []
    for id in nodeState[myself][NODE_NEIGHBOURHOOD]:
        score = get_classification(myself, id, nodeState[myself][CURRENT_CYCLE])
        scores.append([score, id])

    scores.sort()
    nodeState[myself][NODE_NEIGHBOURHOOD_STATS][TOP_N_NODES] = []
    for i in range(0, nodeState[myself][NODES_SIZE][TOP]):
        nodeState[myself][NODE_NEIGHBOURHOOD_STATS][TOP_N_NODES].append(scores[i][1])


def set_timer(myself, target, id, current_cycle):
    if nodeState[myself][NODE_TX_TIMER][target][NOT_SAMPLED] > SAMPLE_SIZE:
        nodeState[myself][NODE_TX_TIMER][target][TIMER_T][id] = [current_cycle, None]
        nodeState[myself][NODE_TX_TIMER][target][NOT_SAMPLED] = 0
    else:
        nodeState[myself][NODE_TX_TIMER][target][NOT_SAMPLED] += 1


def update_timer_lists(myself, target, current_cycle):
    list_to_iter = dict(nodeState[myself][NODE_TX_TIMER][target][TIMER_T])
    for id in list_to_iter:
        if list_to_iter[id][TX_T_CYCLE_RECEIVED] + TIME_FRAME < current_cycle:
            if list_to_iter[id][TX_T_CYCLE_COMMITTED] is None:
                total_time = current_cycle - list_to_iter[id][TX_T_CYCLE_RECEIVED]
            else:
                total_time = list_to_iter[id][TX_T_CYCLE_COMMITTED] - list_to_iter[id][TX_T_CYCLE_RECEIVED]
            nodeState[myself][NODE_TX_TIMER][target][TIMER_T_1][TOTAL_TIME] += total_time
            nodeState[myself][NODE_TX_TIMER][target][TIMER_T_1][TOTAL_SENT] += 1
            del nodeState[myself][NODE_TX_TIMER][target][TIMER_T][id]

    del list_to_iter


def mark_tx_as_received(myself, id):
    for target in nodeState[myself][NODE_TX_TIMER]:
        if id in nodeState[myself][NODE_TX_TIMER][target][TIMER_T]:
            nodeState[myself][NODE_TX_TIMER][target][TIMER_T][id][TX_T_CYCLE_COMMITTED] = nodeState[myself][CURRENT_CYCLE]


def find_block(tx):
    for block in reversed(blocks_created):
        if tx in block[BLOCK_TX]:
            return block[BLOCK_ID]
    return None


def increase_relay(myself):
    now = nodeState[myself][CURRENT_CYCLE]

    if nodeState[myself][HAD_TO_INC][HTI_TIME] + HTI_RESET_TIME < now:
        nodeState[myself][HAD_TO_INC][HTI_BOOL] = False

    to_rem = []
    for tx in nodeState[myself][MY_CONFIRMED_TX]:
        timeout = nodeState[myself][MY_CONFIRMED_TX][tx][CONF_TIME_COMMITTED] + TIME_TO_REM_TX_FROM_CONFIRMED <= now
        if timeout:
            to_rem.append(tx)

    for tx in to_rem:
        del nodeState[myself][MY_CONFIRMED_TX][tx]

    to_rem = []
    for tx in nodeState[myself][MY_UNCONFIRMED_TX]:
        if tx_commit[tx][COMMITTED] and nodeState[myself][MY_UNCONFIRMED_TX][tx] > TIME_FOR_TX_CONFIRMATION * 2:
            to_rem.append(tx)

    for tx in to_rem:
        del nodeState[myself][MY_UNCONFIRMED_TX][tx]

    to_resend = []
    if now > INTERVAL:
        sum_of_all_times = 0
        for tx in nodeState[myself][MY_UNCONFIRMED_TX]:
            timeout = nodeState[myself][MY_UNCONFIRMED_TX][tx] + TIME_FOR_TX_CONFIRMATION <= now
            if timeout and not tx_commit[tx][COMMITTED]:
                to_resend.append(tx)
            sum_of_all_times += now - nodeState[myself][MY_UNCONFIRMED_TX][tx]

        if sum_of_all_times > 0:
            avg = sum_of_all_times / len(nodeState[myself][MY_UNCONFIRMED_TX])
            timeout = avg > TIME_FOR_TX_CONFIRMATION
            if timeout and nodeState[myself][NODES_SIZE][TOP] + 1 <= len(nodeState[myself][NODE_NEIGHBOURHOOD]) // 2 and \
                    nodeState[myself][TIME_SINCE_LAST_INC] + TIME_TO_WAIT_BEFORE_DEC <= now:
                nodeState[myself][NODES_SIZE][TOP] += 1
                nodeState[myself][NODES_SIZE][RAND] += 1
                nodeState[myself][HAD_TO_INC][HTI_BOOL] = True
                up_top(myself)
                nodeState[myself][TIME_SINCE_LAST_INC] = now

        if not nodeState[myself][HAD_TO_INC][HTI_BOOL] and nodeState[myself][TIME_SINCE_LAST_DEC] + TIME_TO_WAIT_BEFORE_DEC <= now:
            sum_of_all_times = 0
            for tx in nodeState[myself][MY_CONFIRMED_TX]:
                sum_of_all_times += nodeState[myself][MY_CONFIRMED_TX][tx][CONF_TIME_IT_TOOK]
            if sum_of_all_times > 0:
                avg = sum_of_all_times / len(nodeState[myself][MY_CONFIRMED_TX])
                timeout = avg <= TIME_FOR_TX_CONFIRMATION
                if timeout and nodeState[myself][NODES_SIZE][TOP] - 1 > 0:
                    nodeState[myself][NODES_SIZE][TOP] -= 1
                    nodeState[myself][NODES_SIZE][RAND] -= 1
                    up_top(myself)
                    nodeState[myself][TIME_SINCE_LAST_DEC] = now

        for tx in to_resend:
            push_to_send(myself, tx, MINE)
# --------------------------------------


# --------------------------------------
# Node inventory management functions
def have_it(myself, type, id):
    global nodeState

    if type != BLOCK_TYPE and type != TX_TYPE:
        print("check_availability strange type {}".format(type))
        exit(-1)

    if (type == BLOCK_TYPE and id in nodeState[myself][NODE_INV][NODE_INV_RECEIVED_BLOCKS]) or \
            (type == TX_TYPE and id in nodeState[myself][NODE_INV][NODE_INV_RECEIVED_TX]):
        return True
    return False


def update_have_it(myself, type, id):
    global nodeState

    if type != BLOCK_TYPE and type != TX_TYPE:
        print("check_availability strange type {}".format(type))
        exit(-1)

    if type == BLOCK_TYPE and id not in nodeState[myself][NODE_INV][NODE_INV_RECEIVED_BLOCKS]:
        nodeState[myself][NODE_INV][NODE_INV_RECEIVED_BLOCKS][id] = nodeState[myself][CURRENT_CYCLE]
        if id in nodeState[myself][NODE_PARTIAL_BLOCKS]:
            nodeState[myself][NODE_PARTIAL_BLOCKS].remove(id)
    elif type == TX_TYPE and id not in nodeState[myself][NODE_INV][NODE_INV_RECEIVED_TX]:
        nodeState[myself][NODE_INV][NODE_INV_RECEIVED_TX][id] = None


def get_header(myself, header_id):
    for header in nodeState[myself][NODE_HEADERS_TO_REQUEST]:
        if header == header_id:
            return header

    return None


# --------------------------------------


# --------------------------------------
# Neighbourhood inventory management functions
def update_neighbourhood_inv(myself, target, type, id):
    global nodeState

    if type != BLOCK_TYPE and type != TX_TYPE:
        print("check_availability strange type {}".format(type))
        exit(-1)

    if type == BLOCK_TYPE and id not in nodeState[myself][NODE_NEIGHBOURHOOD_INV][target][NEIGHBOURHOOD_KNOWN_BLOCKS]:
        if id == -1:
            return
        nodeState[myself][NODE_NEIGHBOURHOOD_INV][target][NEIGHBOURHOOD_KNOWN_BLOCKS].insert(id)
    elif type == TX_TYPE and id not in nodeState[myself][NODE_NEIGHBOURHOOD_INV][target][NEIGHBOURHOOD_KNOWN_TX]:
        nodeState[myself][NODE_NEIGHBOURHOOD_INV][target][NEIGHBOURHOOD_KNOWN_TX][id] = None
        if id in nodeState[myself][NODE_NEIGHBOURHOOD_INV][target][NEIGHBOURHOOD_TX_TO_SEND]:
            del nodeState[myself][NODE_NEIGHBOURHOOD_INV][target][NEIGHBOURHOOD_TX_TO_SEND][id]


def check_availability(myself, target, type, id):
    if type != BLOCK_TYPE and type != TX_TYPE:
        print("check_availability strange type {}".format(type))
        exit(-1)

    if (type == BLOCK_TYPE and (id in nodeState[myself][NODE_NEIGHBOURHOOD_INV][target][NEIGHBOURHOOD_KNOWN_BLOCKS] or id == -1)) \
            or (type == TX_TYPE and id in nodeState[myself][NODE_NEIGHBOURHOOD_INV][target][NEIGHBOURHOOD_KNOWN_TX]):
        return True
    return False


# --------------------------------------


# --------------------------------------
# Transactions related functions
def generate_new_tx(myself):
    global nodeState, tx_id, tx_commit, tx_created_after_last_block

    new_tx = tx_id
    nodeState[myself][NODE_INV][NODE_INV_RECEIVED_TX][new_tx] = None
    nodeState[myself][NODE_MEMPOOL][new_tx] = None
    push_to_send(myself, new_tx, MINE)

    if tx_array:
        tx_created.append([0, 0])
    if nodeState[myself][CURRENT_CYCLE] >= INTERVAL:
        to_append = [nodeState[myself][CURRENT_CYCLE], False, (nodeState[myself][CURRENT_CYCLE]-INTERVAL) // 3600]
    else:
        to_append = [nodeState[myself][CURRENT_CYCLE], False, -1]
    tx_commit.append(to_append)
    tx_created_after_last_block.append(new_tx)
    nodeState[myself][MY_UNCONFIRMED_TX][new_tx] = nodeState[myself][CURRENT_CYCLE]
    tx_id += 1


def get_transaction(myself, tx_id):
    if tx_id in nodeState[myself][NODE_MEMPOOL]:
        return tx_id
    return None


def get_nb_of_tx_to_gen(myself, cycle):
    if myself in nodes_to_gen_tx[cycle]:
        return 1
    return 0


def get_tx_to_block(myself):
    global nodeState

    size = 0
    tx_array = []
    list_to_iter = dict(nodeState[myself][NODE_MEMPOOL])
    for tx in list_to_iter:
        if size + 700 <= max_block_size:
            size += 700
            tx_array.append(tx)
            if not tx_commit[tx][COMMITTED]:
                created = tx_commit[tx][TIME_COMMITTED]
                tx_commit[tx][TIME_COMMITTED] = nodeState[myself][CURRENT_CYCLE] - created
                tx_commit[tx][COMMITTED] = True
            del nodeState[myself][NODE_MEMPOOL][tx]
            for neighbour in nodeState[myself][NODE_NEIGHBOURHOOD]:
                if tx in nodeState[myself][NODE_NEIGHBOURHOOD_INV][neighbour][NEIGHBOURHOOD_TX_TO_SEND]:
                    del nodeState[myself][NODE_NEIGHBOURHOOD_INV][neighbour][NEIGHBOURHOOD_TX_TO_SEND][tx]
        elif size + min_tx_size > max_block_size:
            break
        else:
            continue
    del list_to_iter
    return tx_array


# --------------------------------------


# --------------------------------------
# Broadcast related functions
def update_time_to_send(myself, target):
    global nodeState

    current_cycle = nodeState[myself][CURRENT_CYCLE]
    if nodeState[myself][NODE_TIME_TO_SEND][target][INBOUND]:
        time_increment = poisson_send(current_cycle, 5)
    else:
        time_increment = poisson_send(current_cycle, 2.5)

    nodeState[myself][NODE_TIME_TO_SEND][target][TIME] = time_increment


def poisson_send(cycle, avg_inc):
    if avg_inc == 5:
        return cycle + 5 * random.randrange(3, 5)
    else:
        return cycle + 2.5 * random.randrange(1, 5)


def broadcast_invs(myself):
    global nodeState

    current_cycle = nodeState[myself][CURRENT_CYCLE]
    for target in nodeState[myself][NODE_NEIGHBOURHOOD]:
        time_to_send = nodeState[myself][NODE_TIME_TO_SEND][target][TIME]
        if current_cycle > time_to_send and \
                len(nodeState[myself][NODE_NEIGHBOURHOOD_INV][target][NEIGHBOURHOOD_TX_TO_SEND]) > 0:
            update_time_to_send(myself, target)
            inv_to_send = []
            copy = dict(nodeState[myself][NODE_NEIGHBOURHOOD_INV][target][NEIGHBOURHOOD_TX_TO_SEND])
            counter = 0
            for tx in copy:
                if counter > 35:
                    break
                if not check_availability(myself, target, TX_TYPE, tx):
                    inv_to_send.append((TX_TYPE, tx))
                    update_neighbourhood_inv(myself, target, TX_TYPE, tx)
                    if hop_based_broadcast and timer_solution:
                        set_timer(myself, target, tx, current_cycle)
                    counter += 1
            del copy
            sim.send(INV, target, myself, inv_to_send)
            if should_log(myself):
                nodeState[myself][MSGS][INV_MSG][SENT] += 1


def push_to_send(myself, id, mine):
    global nodeState

    if not hop_based_broadcast or mine and hop_based_broadcast and early_push or \
            hop_based_broadcast and nodeState[myself][CURRENT_CYCLE] < 18000:
        nodes_to_send = nodeState[myself][NODE_NEIGHBOURHOOD]
    else:
        nodes_to_send = get_nodes_to_send(myself)

    for node in nodes_to_send:
        if not check_availability(myself, node, TX_TYPE, id) and \
                id not in nodeState[myself][NODE_NEIGHBOURHOOD_INV][node][NEIGHBOURHOOD_TX_TO_SEND]:
            nodeState[myself][NODE_NEIGHBOURHOOD_INV][node][NEIGHBOURHOOD_TX_TO_SEND][id] = None


def get_nodes_to_send(myself):
    if not nodeState[myself][NODE_NEIGHBOURHOOD_STATS][TOP_N_NODES]:
        return nodeState[myself][NODE_NEIGHBOURHOOD]

    total = nodeState[myself][NODES_SIZE][TOP] + nodeState[myself][NODES_SIZE][RAND]
    top_nodes = nodeState[myself][NODE_NEIGHBOURHOOD_STATS][TOP_N_NODES]
    if len(nodeState[myself][NODE_NEIGHBOURHOOD]) < total:
        total = len(nodeState[myself][NODE_NEIGHBOURHOOD]) - len(top_nodes)
    else:
        total = total - len(top_nodes)

    random_nodes = []
    if total > 0:
        collection_of_neighbours = list(nodeState[myself][NODE_NEIGHBOURHOOD])
        for node in top_nodes:
            if node in collection_of_neighbours:
                collection_of_neighbours.remove(node)
        random_nodes = random.sample(collection_of_neighbours, total)
        del collection_of_neighbours

    return top_nodes + random_nodes


# --------------------------------------


def next_t_to_gen(myself):
    global nodeState

    y = numpy.random.normal(0.6, 0.11)
    if y > 1:
        x = - 10 * numpy.log(1 - 0.99)
    elif y < 0:
        x = - 10 * numpy.log(1 - 0.01)
    else:
        x = - 10 * numpy.log(1 - y)

    for tuple in values:
        if tuple[0] <= x < tuple[1]:
            nodeState[myself][NODE_TIME_TO_GEN] += tuple[2]
            return


def should_log(myself):
    if (expert_log and INTERVAL < nodeState[myself][CURRENT_CYCLE] < nb_cycles - INTERVAL) or not expert_log:
        return True
    return False


def update_tx(myself, block):
    global nodeState

    for tx in block[BLOCK_TX]:
        if tx in nodeState[myself][NODE_MEMPOOL]:
            del nodeState[myself][NODE_MEMPOOL][tx]

        if tx in nodeState[myself][MY_UNCONFIRMED_TX]:
            now = nodeState[myself][CURRENT_CYCLE]
            nodeState[myself][MY_CONFIRMED_TX][tx] = [now, now - nodeState[myself][MY_UNCONFIRMED_TX][tx]]
            del nodeState[myself][MY_UNCONFIRMED_TX][tx]

        for neighbour in nodeState[myself][NODE_NEIGHBOURHOOD]:
            update_neighbourhood_inv(myself, neighbour, TX_TYPE, tx)

        if tx in nodeState[myself][NODE_TX_ALREADY_REQUESTED]:
            nodeState[myself][NODE_TX_ALREADY_REQUESTED].remove(tx)

        if hop_based_broadcast and timer_solution:
            mark_tx_as_received(myself, tx)


def new_connection(myself, source):
    global nodeState

    if len(nodeState[myself][NODE_NEIGHBOURHOOD]) > 125:
        raise ValueError("Number of connections in one node exceed the maximum allowed")

    if source in nodeState[myself][NODE_NEIGHBOURHOOD]:
        return
    else:
        nodeState[myself][NODE_NEIGHBOURHOOD].append(source)
        nodeState[myself][NODE_NEIGHBOURHOOD_INV][source] = [SortedCollection(), defaultdict(), defaultdict()]
        nodeState[myself][NODE_NEIGHBOURHOOD_STATS][STATS][source] = [[[], 0], [0, 0]]
        nodeState[myself][NODE_TIME_TO_SEND][source] = [poisson_send(nodeState[myself][CURRENT_CYCLE], 5), True]
        nodeState[myself][NODE_TX_TIMER][source] = [0, defaultdict(), [0, 0]]


# --------------------------------------
# Start up functions
def create_network(create_new, save_network_connections, neighbourhood_size, filename=""):
    global nb_nodes, nodeState, miners

    first_time = not os.path.exists("networks/")
    network_first_time = not os.path.exists("networks/" + filename)

    if first_time:
        os.makedirs("networks/")

    if network_first_time or create_new:
        create_nodes_and_miners(neighbourhood_size)
        create_miner_replicas(neighbourhood_size)
        if save_network_connections:
            save_network()
    else:
        load_network(filename)
    create_bad_node()


def save_network():
    with open('networks/{}-{}-{}'.format(nb_nodes - (number_of_miners * extra_replicas), number_of_miners, extra_replicas), 'w') \
            as file_to_write:
        file_to_write.write("{} {} {}\n".format(nb_nodes, number_of_miners, extra_replicas))
        for n in range(nb_nodes):
            file_to_write.write(str(nodeState[n][NODE_NEIGHBOURHOOD]) + '\n')
        file_to_write.write(str(miners) + '\n')


def load_network(filename):
    global nodeState, nb_nodes, number_of_miners, extra_replicas, miners, bad_nodes

    if filename == "":
        raise ValueError("No file named inputted in not create new run")

    with open('networks/' + filename, 'r') as file_to_read:
        first_line = file_to_read.readline()
        nb_nodes, number_of_miners, extra_replicas = first_line.split()
        nb_nodes, number_of_miners, extra_replicas = int(nb_nodes), int(number_of_miners), int(extra_replicas)
        nodeState = defaultdict()
        for n in range(nb_nodes):
            nodeState[n] = createNode(ast.literal_eval(file_to_read.readline()))
        miners = ast.literal_eval(file_to_read.readline())


def createNode(neighbourhood):
    current_cycle = 0
    node_current_block = None
    node_inv = [defaultdict(), defaultdict()]
    node_partial_blocks = []
    node_mempool = defaultdict()
    node_blocks_already_requested = []
    node_tx_already_requested = []
    node_time_to_gen = -1
    node_neighbourhood_inv = defaultdict()
    stats = defaultdict()
    time_to_send = defaultdict()
    topx = []
    node_headers_requested = []
    timer = defaultdict()
    for neighbour in neighbourhood:
        node_neighbourhood_inv[neighbour] = [SortedCollection(), defaultdict(), defaultdict()]
        stats[neighbour] = [[[], 0], [0, 0]]
        time_to_send[neighbour] = [poisson_send(0, 2.5), False]
        timer[neighbour] = [0, defaultdict(), [0, 0]]
    node_neighbourhood_stats = [topx, stats]
    node_top_nodes_size = [top_nodes_size, random_nodes_size]
    my_unconfirmed_tx = defaultdict()
    my_confirmed_tx = defaultdict()
    has_to_inc = [False, 0]
    time_since_last_dec = 0
    time_since_last_inc = 0

    depth = 0

    msgs = [[0, 0], 0, 0, [0, 0], 0, 0, 0, 0, 0, 0, [0, 0, 0]]

    return [current_cycle, node_current_block, node_inv, node_partial_blocks, node_mempool,
            node_blocks_already_requested, node_tx_already_requested, node_time_to_gen, neighbourhood,
            node_neighbourhood_inv, node_neighbourhood_stats, msgs, node_headers_requested, time_to_send, timer,
            node_top_nodes_size, my_unconfirmed_tx, my_confirmed_tx, has_to_inc, time_since_last_dec, time_since_last_inc, depth]


def create_nodes_and_miners(neighbourhood_size):
    global nodeState, miners

    nodeState = defaultdict()
    for n in range(nb_nodes):
        neighbourhood = random.sample(range(nb_nodes), neighbourhood_size)
        while neighbourhood.__contains__(n):
            neighbourhood = random.sample(range(nb_nodes), neighbourhood_size)
        nodeState[n] = createNode(neighbourhood)

    miners = random.sample(range(nb_nodes), number_of_miners)


def create_miner_replicas(neighbourhood_size):
    global nb_nodes, nodeState, miners

    if extra_replicas > 0:
        i = 0
        miners_to_add = []
        for n in range(nb_nodes, nb_nodes + (extra_replicas * number_of_miners)):
            neighbourhood = random.sample(range(nb_nodes), neighbourhood_size)
            while neighbourhood.__contains__(n) or neighbourhood.__contains__(miners[i]):
                neighbourhood = random.sample(range(nb_nodes), neighbourhood_size)
            neighbourhood.append(miners[i])
            nodeState[n] = createNode(neighbourhood)
            miners_to_add.append(n)
            i += 1
            if i == number_of_miners - 1:
                i = 0
        miners = miners + miners_to_add

        nb_nodes = nb_nodes + (extra_replicas * number_of_miners)


def create_bad_node():
    global bad_nodes

    bad_nodes = random.sample(range(nb_nodes), int((number_of_bad_nodes / 100) * nb_nodes))


def configure(config):
    global nb_nodes, nb_cycles, nodeState, node_cycle, block_id, tx_id, \
        number_of_tx_to_gen_per_cycle, max_block_size, min_tx_size, max_tx_size, values, nodes_to_gen_tx, miners, \
        top_nodes_size, hop_based_broadcast, number_of_miners, extra_replicas, blocks_created, blocks_mined_by_randoms, \
        total_blocks_mined_by_randoms, highest_block, random_nodes_size, tx_created, tx_array, expert_log, bad_nodes, \
        number_of_bad_nodes, tx_commit, tx_created_after_last_block, timer_solution

    node_cycle = int(config['NODE_CYCLE'])

    nb_nodes = config['NUMBER_OF_NODES']
    neighbourhood_size = int(config['NEIGHBOURHOOD_SIZE'])
    if top_nodes != -1:
        if top_nodes == 0:
            hop_based_broadcast = False
        else:
            hop_based_broadcast = True
            if not timer_solution:
                timer_solution = bool(config['TIMER_SOLUTION'])
        top_nodes_size = top_nodes
        if random_nodes != -1:
            random_nodes_size = random_nodes
        else:
            random_nodes_size = top_nodes
    else:
        top_nodes_size = int(config['TOP_NODES_SIZE'])
        random_nodes_size = int(config['RANDOM_NODES_SIZE'])
        hop_based_broadcast = bool(config['HOP_BASED_BROADCAST'])
        if not timer_solution:
            timer_solution = bool(config['TIMER_SOLUTION'])

    if number_of_bad_nodes == 0:
        number_of_bad_nodes = int(config['NUMBER_OF_BAD_NODES'])

    number_of_miners = int(config['NUMBER_OF_MINERS'])
    extra_replicas = int(config['EXTRA_REPLICAS'])

    nb_cycles = config['NUMBER_OF_CYCLES']
    max_block_size = int(config['MAX_BLOCK_SIZE'])

    tx_array = bool(config['TX_ARRAY'])
    number_of_tx_to_gen_per_cycle = config['NUMB_TX_PER_CYCLE']
    min_tx_size = int(config['MIN_TX_SIZE'])
    max_tx_size = int(config['MAX_TX_SIZE'])
    blocks_mined_by_randoms = 0
    total_blocks_mined_by_randoms = (nb_cycles / 10) * 0.052

    expert_log = bool(config['EXPERT_LOG'])
    if nb_cycles <= INTERVAL:
        raise ValueError("You have to complete more than {} cycles".format(INTERVAL))

    block_id = 0
    blocks_created = []
    highest_block = -1
    tx_id = 0
    tx_created = []
    tx_commit = []
    tx_created_after_last_block = []

    values = []
    i = -1
    j = 20 * 60
    while i < 20:
        values.append((i, i + 1, j))
        i += 1
        j -= 60

    create_network(create_new, save_network_connections, neighbourhood_size, file_name)

    if number_of_tx_to_gen_per_cycle // nb_nodes == 0:
        nodes_to_gen_tx = []
        for i in range(0, nb_cycles):
            nodes_to_gen_tx.append(random.sample(range(nb_nodes), number_of_tx_to_gen_per_cycle))

    IS_CHURN = config.get('CHURN', False)
    if IS_CHURN:
        CHURN_RATE = config.get('CHURN_RATE', 0.)
    MESSAGE_LOSS = float(config.get('MESSASE_LOSS', 0))
    if MESSAGE_LOSS > 0:
        sim.setMessageLoss(MESSAGE_LOSS)

    nodeDrift = int(nb_cycles * float(config['NODE_DRIFT']))
    latencyTablePath = config['LATENCY_TABLE']
    latencyValue = None

    try:
        with open(latencyTablePath, 'r') as f:
            latencyTable = pickle.load(f)
    except:
        latencyTable = None
        latencyValue = int(latencyTablePath)
        logger.warn('Using constant latency value: {}'.format(latencyValue))

    latencyTable = utils.check_latency_nodes(latencyTable, nb_nodes, latencyValue)
    latencyDrift = eval(config['LATENCY_DRIFT'])

    sim.init(node_cycle, nodeDrift, latencyTable, latencyDrift)


# --------------------------------------


# --------------------------------------
# Wrap up functions
def get_all_genesis():
    genesis = []
    for block in blocks_created:
        if block[BLOCK_HEIGHT] == 0 and block[BLOCK_ID] not in genesis:
            genesis.append(block[BLOCK_ID])
    return genesis


def fork_rate():
    branches = get_all_genesis()
    all_blocks = list(range(0, block_id))
    i = 0

    while len(all_blocks) != 0:
        current_block = branches[i]
        all_blocks.remove(current_block)
        found = False

        for potential_block in blocks_created:
            if potential_block[BLOCK_PARENT_ID] == current_block and potential_block[BLOCK_ID] not in branches:
                found = True
                branches.append(potential_block[BLOCK_ID])

        if len(all_blocks) == 0:
            break

        if not found:
            i += 1
        elif found:
            branches.pop(i)

    return len(branches)


def get_miner_hops():
    seen = {}
    depth = 0
    for miner in miners:
        seen[miner] = depth

    to_call = list(miners)
    called = list(miners)
    seen = count_hops(to_call, called, seen, depth)

    further = numpy.amax(seen.values())
    counter = [0] * (further + 1)
    for node in seen.keys():
        counter[seen[node]] += 1
        nodeState[node][DEPTH] = seen[node]

    return counter


def count_hops(to_call, called, seen, depth):
    if len(to_call) == 0:
        return seen

    dup_to_call = list(to_call)
    for calling in dup_to_call:
        called.append(calling)
        to_call.remove(calling)
        if calling not in seen.keys() or seen[calling] > depth:
            seen[calling] = depth

        for neighbour in nodeState[calling][NODE_NEIGHBOURHOOD]:
            if neighbour not in called and neighbour not in to_call:
                to_call.append(neighbour)

    return count_hops(to_call, called, seen, depth + 1)


def get_avg_tx_per_block():
    total_num_if_tx = 0
    blocks_not_counted = 0
    for block in blocks_created:
        if (expert_log and INTERVAL < block[BLOCK_TIMESTAMP] < nb_cycles - INTERVAL) or not expert_log:
            if isinstance(block[BLOCK_TX], int):
                total_num_if_tx += block[BLOCK_TX]
            else:
                total_num_if_tx += len(block[BLOCK_TX])
        elif expert_log:
            blocks_not_counted += 1

    return total_num_if_tx / (block_id - blocks_not_counted)


def get_avg_total_sent_msg():
    total_sent = [0] * nb_nodes
    for node in range(nb_nodes):
        for i in range(INV_MSG, MISSING_TX):
            if i == 0 or i == 3:
                total_sent[node] += nodeState[node][MSGS][i][SENT]
            else:
                total_sent[node] += nodeState[node][MSGS][i]

    total_sent = sum(total_sent)

    return total_sent / nb_nodes


def get_nb_tx_added_to_blocks():
    counter = 0
    for tx in tx_commit:
        if tx[COMMITTED]:
            counter += 1
    return counter


def get_nb_of_tx_gened():
    tx_in_miners = []
    for myself in miners:
        for tx in nodeState[myself][NODE_MEMPOOL]:
            if tx not in tx_created_after_last_block and not tx_commit[tx][COMMITTED] and tx not in tx_in_miners:
                tx_in_miners.append(tx)

    return tx_id - len(tx_created_after_last_block) - len(tx_in_miners)


def get_avg_time_committed():
    counter = 0
    sum = 0
    for tx in tx_commit:
        if tx[COMMITTED]:
            sum += tx[TIME_COMMITTED]
            counter += 1
    return sum / counter


def get_nodes_per_conf():
    if not hop_based_broadcast:
        return None

    results = defaultdict()
    for myself in nodeState:
        conf = "TOP-" + str(nodeState[myself][NODES_SIZE][TOP])
        if conf in results:
            results[conf] += 1
        else:
            results[conf] = 1

    to_return = []
    for key in results.keys():
        to_return.append([key, results[key]])

    return sorted(to_return)


def get_conf_per_dist(counter):
    if not hop_based_broadcast:
        return None

    resutls = defaultdict()
    for depth in range(0, len(counter)):
        for node in nodeState:
            if nodeState[node][DEPTH] == depth:
                config = "TOP-" + str(nodeState[node][NODES_SIZE][TOP])
                if depth in resutls:
                    if config in resutls[depth]:
                        resutls[depth][config] += 1
                    else:
                        resutls[depth][config] = 1

                else:
                    resutls[depth] = defaultdict()
                    resutls[depth][config] = 1

    to_return = []
    for depth in sorted(resutls):
        tmp = []
        for config in sorted(resutls[depth]):
            tmp.append([config, resutls[depth][config]])
        to_return.append(tmp)

    return to_return


def commits_per_time():
    dic = defaultdict()
    for tx in tx_commit:
        if tx[COMMITTED] and tx[2] > 0:
            if tx[2] in dic:
                dic[tx[2]][0] += tx[TIME_COMMITTED]
                dic[tx[2]][1] += 1
            else:
                dic[tx[2]] = [tx[TIME_COMMITTED], 1]

    to_return = []
    for i in range(0, max(dic.keys())):
        if i in dic.keys():
            to_return.append(dic[i][0]/dic[i][1])
        else:
            to_return.append(0)

    return to_return


def wrapup():
    global nodeState

    inv_messages = list(map(lambda x: nodeState[x][MSGS][INV_MSG], nodeState))
    getheaders_messages = list(map(lambda x: nodeState[x][MSGS][GETHEADERS_MSG], nodeState))
    headers_messages = list(map(lambda x: nodeState[x][MSGS][HEADERS_MSG], nodeState))
    getdata_messages = list(map(lambda x: nodeState[x][MSGS][GETDATA_MSG], nodeState))
    block_messages = list(map(lambda x: nodeState[x][MSGS][BLOCK_MSG], nodeState))
    cmpctblock_messages = list(map(lambda x: nodeState[x][MSGS][CMPCTBLOCK_MSG], nodeState))
    getblocktx_messages = list(map(lambda x: nodeState[x][MSGS][GETBLOCKTXN_MSG], nodeState))
    blocktx_messages = list(map(lambda x: nodeState[x][MSGS][BLOCKTXN_MSG], nodeState))
    tx_messages = list(map(lambda x: nodeState[x][MSGS][TX_MSG], nodeState))
    missing_tx = list(map(lambda x: nodeState[x][MSGS][MISSING_TX], nodeState))
    all_inv = list(map(lambda x: nodeState[x][MSGS][ALL_INVS][RECEIVED_INV], nodeState))
    relevant_inv = list(map(lambda x: nodeState[x][MSGS][ALL_INVS][RELEVANT_INV], nodeState))
    all_getdata = list(map(lambda x: nodeState[x][MSGS][ALL_INVS][RECEIVED_GETDATA], nodeState))
    sum_received_blocks = list(map(lambda x: nodeState[x][NODE_INV][NODE_INV_RECEIVED_BLOCKS], nodeState))
    # receivedBlocks = map(lambda x: map(lambda y: (sum_received_blocks[x][y][0], sum_received_blocks[x][y][1],
    #                                              sum_received_blocks[x][y][2], sum_received_blocks[x][y][3],
    #                                              sum_received_blocks[x][y][4], sum_received_blocks[x][y][6]),
    #                                   range(len(sum_received_blocks[x]))), nodeState)

    # dump data into gnuplot format
    utils.dump_as_gnu_plot([inv_messages, getheaders_messages, headers_messages, getdata_messages, block_messages,
                            cmpctblock_messages, getblocktx_messages, blocktx_messages, tx_messages, sum_received_blocks],
                           dumpPath + '/messages-' + str(runId) + '.gpData',
                           ['inv getheaders headers getdata block cmpctblock getblocktx blocktx tx'
                            '           sum_received_blocks                    receivedBlocks'])

    sum_inv = 0
    sum_getData = 0
    sum_tx = 0
    sum_getBlockTX = 0
    sum_missingTX = 0
    sum_all_inv = 0
    sum_relevant_inv = 0
    sum_received_invs = 0
    sum_received_getdata = 0
    sum_all_getdata = 0
    for i in range(0, nb_nodes):
        sum_inv += inv_messages[i][SENT]
        sum_received_invs += inv_messages[i][RECEIVED]
        sum_getData += getdata_messages[i][SENT]
        sum_received_getdata += getdata_messages[i][RECEIVED]
        sum_tx += tx_messages[i]
        sum_getBlockTX += getblocktx_messages[i]
        sum_missingTX += missing_tx[i]
        sum_all_inv += all_inv[i]
        sum_relevant_inv += relevant_inv[i]
        sum_all_getdata += all_getdata[i]

    # avg_block_diss = avg_block_dissemination()
    nb_forks = fork_rate()
    hops_distribution = get_miner_hops()
    avg_tx_per_block = get_avg_tx_per_block()
    avg_total_sent_msg = get_avg_total_sent_msg()
    # ---------
    if sum_all_inv == 0:
        avg_duplicated_inv = 0
        avg_entries_per_inv = 0
    else:
        avg_duplicated_inv = sum_all_inv / sum_relevant_inv
        avg_entries_per_inv = sum_all_inv / sum_received_invs
    # ---------
    if sum_all_getdata == 0:
        avg_entries_per_getdata = 0
    else:
        avg_entries_per_getdata = sum_all_getdata / sum_received_getdata

    nb_tx_added_to_blocks = get_nb_tx_added_to_blocks()
    nb_of_tx_gened = get_nb_of_tx_gened()
    avg_time_commited = get_avg_time_committed()

    nodes_per_conf = get_nodes_per_conf()

    confs_per_depth = get_conf_per_dist(hops_distribution)

    commits_per_min = commits_per_time()

    data = []
    for tx in tx_commit:
        if tx[COMMITTED]:
            data.append(tx[TIME_COMMITTED])

    time_commited_CDF = utils.percentiles(data, percs=range(101), paired=False)

    utils.dump_as_gnu_plot([time_commited_CDF], dumpPath + '/time_commited_CDF-' + str(runId) + '.gpData', ['time_commited'])

    first_time = not os.path.isfile('out/{}.csv'.format(results_name))
    if first_time:
        csv_file_to_write = open('out/results.csv', 'w')
        spam_writer = csv.writer(csv_file_to_write, delimiter=',', quotechar='\'', quoting=csv.QUOTE_MINIMAL)
        spam_writer.writerow(["Number of nodes", "Number of cycles", "Number of miners", "Extra miners"])
        spam_writer.writerow([nb_nodes, nb_cycles, number_of_miners, extra_replicas])
        spam_writer.writerow(["Bitcoin", "Early push", "Bad nodes", "Avg inv", "Avg entries per inv", "Avg getData", "Avg entries per getData",
                              "Avg Tx", "Avg getBlockTX", "Avg missing tx", "Avg numb of tx per block", "% of duplicates inv",
                              "Avg total sent messages", "Total tx created", "Total tx added to blocks", "Avg commit time",
                              "Total number of branches", "Total blocks created", "Hops distribution"])
    else:
        csv_file_to_write = open('out/results.csv', 'a')
        spam_writer = csv.writer(csv_file_to_write, delimiter=',', quotechar='\'', quoting=csv.QUOTE_MINIMAL)

    spam_writer.writerow([not hop_based_broadcast, early_push, number_of_bad_nodes, sum_inv / nb_nodes, avg_entries_per_inv, sum_getData / nb_nodes,
                          avg_entries_per_getdata, sum_tx / nb_nodes, sum_getBlockTX / nb_nodes, sum_missingTX / nb_nodes, avg_tx_per_block,
                          avg_duplicated_inv, avg_total_sent_msg, nb_of_tx_gened, nb_tx_added_to_blocks, avg_time_commited, nb_forks, block_id,
                          ''.join(str(e) + " " for e in hops_distribution)])
    csv_file_to_write.flush()
    csv_file_to_write.close()
    utils.dump_as_gnu_plot([commits_per_min], 'out/commits_per_time-' + str(runId) + '.gpData', ['time_commited'])

    if hop_based_broadcast:
        csv_file_to_write = open('out/{}.csv'.format("new-stats-" + str(runId)), 'w')
        spam_writer = csv.writer(csv_file_to_write, delimiter=',', quotechar='\'', quoting=csv.QUOTE_MINIMAL)
        for conf in nodes_per_conf:
            spam_writer.writerow([conf[0], conf[1]])
        for depth in range(0, len(confs_per_depth)):
            spam_writer.writerow([depth])
            for conf in confs_per_depth[depth]:
                spam_writer.writerow([conf[0], conf[1]])
        csv_file_to_write.flush()
        csv_file_to_write.close()

# --------------------------------------


if __name__ == '__main__':

    # setup logger
    logger = logging.getLogger(__file__)
    logger.setLevel(logging.DEBUG)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)

    logger.addHandler(console)

    if len(sys.argv) < 3:
        logger.error("Invocation: ./echo.py <conf_file> <run_id>")
        sys.exit()

    if not os.path.exists("out/"):
        os.makedirs("out/")
    output = open("output.txt", 'a')

    dumpPath = sys.argv[1]
    confFile = dumpPath + '/conf.yaml'
    runId = int(sys.argv[2])
    f = open(confFile)

    gc.enable()

    top_nodes = -1
    random_nodes = -1
    create_new = True
    early_push = False
    save_network_connections = False
    file_name = ""
    results_name = "results"
    number_of_bad_nodes = 0
    timer_solution = False
    if len(sys.argv) > 3:
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "-cn":
                create_new = sys.argv[i + 1]
            elif sys.argv[i] == "-sn":
                save_network_connections = sys.argv[i + 1]
            elif sys.argv[i] == "-tn":
                top_nodes = int(sys.argv[i + 1])
            elif sys.argv[i] == "-rn":
                random_nodes = int(sys.argv[i + 1])
            elif sys.argv[i] == "-ln":
                create_new = False
                save_network_connections = False
                file_name = sys.argv[i + 1]
            elif sys.argv[i] == "-rsn":
                results_name = sys.argv[i + 1]
            elif sys.argv[i] == "-ep":
                early_push = sys.argv[i + 1]
            elif sys.argv[i] == "-bn":
                number_of_bad_nodes = int(sys.argv[i + 1])
            elif sys.argv[i] == "-ts":
                timer_solution = sys.argv[i + 1]
            else:
                raise ValueError("Input {} is invalid".format(sys.argv[i]))
            i += 2

    if not create_new and file_name == "":
        raise ValueError("Invalid combination of inputs create_new and file_name")

    # load configuration file
    yaml.safe_load(f)
    logger.info('Configuration done')

    # start simulation
    init()
    logger.info('Init done')
    # run the simulation
    sim.run()
    logger.info('Run done')
    # finish simulation, compute stats
    output.close()
    wrapup()
    logger.info("That's all folks!")
