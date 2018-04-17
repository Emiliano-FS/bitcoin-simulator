# Sample simulator demo
# Miguel Matos - miguel.marques.matos@tecnico.ulisboa.pt
# (c) 2012-2018

from collections import defaultdict
import math
import random
import sys
import os

import yaml
import cPickle
import logging

from sim import sim
import utils

LOG_TO_FILE = False


def init():
    global nodeState

    # schedule execution for all nodes
    for nodeId in nodeState:
        sim.schedulleExecution(CYCLE, nodeId)

    # other things such as periodic measurements can also be scheduled
    # to schedulle periodic measurements use the following
    # for c in range(nbCycles * 10):
    #    sim.schedulleExecutionFixed(MEASURE_X, nodeCycle * (c + 1))


def CYCLE(myself):
    global nodeState, block_id, max_block_number

    # with churn the node might be gone
    if myself not in nodeState:
        return

    # show progress for one node
    if myself == 0:
        logger.info('node {} cycle {}'.format(myself, nodeState[myself][CURRENT_CYCLE]))

    nodeState[myself][CURRENT_CYCLE] += 1

    # schedule next execution
    if nodeState[myself][CURRENT_CYCLE] < nbCycles:
        sim.schedulleExecution(CYCLE, myself)

    # select random node to send message
    # assume global view
    if random.random() <= probBroadcast and block_id < max_block_number:
        nodeState[myself][RECEIVED_BLOCKS].append(block_id)
        for target in nodeState[myself][NEIGHBOURHOOD]:
            sim.send(INV, target, myself, "hello, i am {} and I have this header".format(myself), block_id)
            nodeState[myself][BLOCKS_AVAILABILITY].setdefault(target, []).append(block_id)
            nodeState[myself][MSGS_SENT] += 1
        block_id += 1


def INV(myself, source, msg1, block_id):
    global nodeState
    nodeState[myself][BLOCKS_AVAILABILITY].setdefault(source, []).append(block_id)

    # TODO it does send inventory not headers
    logger.info("Node {} Received {} from {} with {}".format(myself, msg1, source, block_id))
    nodeState[myself][MSGS_RECEIVED] += 1
    if block_id not in nodeState[myself][RECEIVED_BLOCKS]:
        sim.send(GETHEADERS, source, myself, "Give me your headers", block_id)


def GETHEADERS(myself, source, msg1, msg2):
    global nodeState

    logger.info("Node {} Received {} from {} with {}".format(myself, msg1, source, msg2))
    nodeState[myself][MSGS_RECEIVED] += 1
    sim.send(HEADERS, source, myself, "Here are my headers", msg2)


def HEADERS(myself, source, msg1, msg2):
    global nodeState

    logger.info("Node {} Received {} from {} with {}".format(myself, msg1, source, msg2))
    nodeState[myself][MSGS_RECEIVED] += 1
    sim.send(GETDATA, source, myself, "Give me these blocks", msg2)


def GETDATA(myself, source, msg1, msg2):
    global nodeState

    logger.info("Node {} Received {} from {} with {}".format(myself, msg1, source, msg2))
    nodeState[myself][MSGS_RECEIVED] += 1
    sim.send(BLOCK, source, myself, "These are the blocks requested", msg2)
    nodeState[myself][BLOCKS_AVAILABILITY].setdefault(source, []).append(msg2)


def BLOCK(myself, source, msg1, block_id):
    global nodeState

    logger.info("Node {} Received {} from {} with {}".format(myself, msg1, source, block_id))
    nodeState[myself][MSGS_RECEIVED] += 1
    PROCESSBLOCK(myself, source, block_id)


def PROCESSBLOCK(myself, source, block_id):
    if block_id not in nodeState[myself][RECEIVED_BLOCKS]:
        nodeState[myself][RECEIVED_BLOCKS].append(block_id)
        for target in nodeState[myself][NEIGHBOURHOOD]:
            if target == source:
                continue
            if target in nodeState[myself][BLOCKS_AVAILABILITY] and block_id-1 in nodeState[myself][BLOCKS_AVAILABILITY][target]:
                sim.send(CMPCTBLOCK, target, myself, "Here it is the most recent block".format(myself), block_id)
                nodeState[myself][BLOCKS_AVAILABILITY].setdefault(target, []).append(block_id)
            else:
                sim.send(INV, target, myself, "hello, i am {} and I have this headers".format(myself), block_id)
            nodeState[myself][MSGS_SENT] += 1


def CMPCTBLOCK(myself, source, msg1, block_id):
    global nodeState

    logger.info("Node {} Received {} from {} with {}".format(myself, msg1, source, block_id))
    nodeState[myself][MSGS_RECEIVED] += 1
    PROCESSBLOCK(myself, source, block_id)


def GETBLOCKTXN(myself, source, msg1, msg2):
    global nodeState

    logger.info("Node {} Received {} from {} with {}".format(myself, msg1, source, msg2))
    nodeState[myself][MSGS_RECEIVED] += 1
    sim.send(BLOCKTXN, source, myself, "These are the transactions requested", "Block")


def BLOCKTXN(myself, source, msg1, msg2):
    global nodeState

    logger.info("Node {} Received {} from {} with {}".format(myself, msg1, source, msg2))
    nodeState[myself][MSGS_RECEIVED] += 1


def wrapup():
    global nodeState
    logger.info("Wrapping up")
    logger.info(nodeState)

    receivedMessages = map(lambda x: nodeState[x][MSGS_RECEIVED], nodeState)
    sentMessages = map(lambda x: nodeState[x][MSGS_SENT], nodeState)
    receivedBlocks = map(lambda x: nodeState[x][RECEIVED_BLOCKS], nodeState)

    # gather some stats, see utils for more functions
    logger.info("receivedMessages {}".format(receivedMessages))
    logger.info("receivedMessages min: {}, max: {}, total: {}".format(min(receivedMessages), max(receivedMessages),
                                                                      sum(receivedMessages)))
    logger.info("sentMessages {}".format(sentMessages))
    logger.info(
        "sentMessages min: {}, max: {}, total: {}".format(min(sentMessages), max(sentMessages), sum(receivedMessages)))

    # dump data into gnuplot format
    utils.dumpAsGnuplot([receivedMessages, sentMessages, receivedBlocks],
                        dumpPath + '/messages-' + str(runId) + '.gpData',
                        ['receivedMessages sentMessages receivedBlocks'])

    # dump data for later processing
    with open(dumpPath + '/dumps-' + str(runId) + '.obj', 'w') as f:
        cPickle.dump(receivedMessages, f)
        cPickle.dump(sentMessages, f)


def createNode(neighbourhood):
    # maintain the node state as a list with the required variables
    # a dictionary is more readable but performance drop is considerable
    global CURRENT_CYCLE
    global MSGS_RECEIVED
    global MSGS_SENT
    global NEIGHBOURHOOD
    global RECEIVED_BLOCKS
    global BLOCKS_AVAILABILITY

    CURRENT_CYCLE, MSGS_RECEIVED, MSGS_SENT, NEIGHBOURHOOD, RECEIVED_BLOCKS, BLOCKS_AVAILABILITY = 0, 1, 2, 3, 4, 5
    return [0, 0, 0, neighbourhood, [], {}]


def configure(config):
    global nbNodes, nbCycles, probBroadcast, nodeState, nodeCycle, block_id, max_block_number

    IS_CHURN = config.get('CHURN', False)
    if IS_CHURN:
        CHURN_RATE = config.get('CHURN_RATE', 0.)
    MESSAGE_LOSS = float(config.get('MESSASE_LOSS', 0))
    if MESSAGE_LOSS > 0:
        sim.setMessageLoss(MESSAGE_LOSS)

    nbNodes = config['nbNodes']
    probBroadcast = config['probBroadcast']
    nbCycles = config['nbCycles']

    IS_CHURN = config.get('CHURN', False)

    latencyTablePath = config['LATENCY_TABLE']
    latencyValue = None
    try:
        with open(latencyTablePath, 'r') as f:
            latencyTable = cPickle.load(f)
    except:
        latencyTable = None
        latencyValue = int(latencyTablePath)
        logger.warn('Using constant latency value: {}'.format(latencyValue))

    latencyTable = utils.checkLatencyNodes(latencyTable, nbNodes, latencyValue)
    latencyDrift = eval(config['LATENCY_DRIFT'])

    IS_CHURN = config.get('CHURN', False)

    nodeCycle = int(config['NODE_CYCLE'])
    rawNodeDrift = float(config['NODE_DRIFT'])
    nodeDrift = int(nodeCycle * float(config['NODE_DRIFT']))
    neighbourhood_size = int(config['NEIGHBOURHOOD_SIZE'])

    block_id = 0
    max_block_number = int(config['MAX_NUMBER_OF_BLOCKS'])
    nodeState = defaultdict()
    for n in xrange(nbNodes):
        neighbourhood = random.sample(xrange(nbNodes), neighbourhood_size)
        while neighbourhood.__contains__(n):
            neighbourhood = random.sample(xrange(nbNodes), neighbourhood_size)
        nodeState[n] = createNode(neighbourhood)

    sim.init(nodeCycle, nodeDrift, latencyTable, latencyDrift)


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

    if LOG_TO_FILE:
        if not os.path.exists("logs/"):
            os.makedirs("logs/")
            # logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG, filename='logs/echo.log', filemode='w')
    dumpPath = sys.argv[1]
    confFile = dumpPath + '/conf.yaml'
    runId = int(sys.argv[2])
    f = open(confFile)

    # load configuration file
    configure(yaml.load(f))
    logger.info('Configuration done')

    # start simulation
    init()
    logger.info('Init done')
    # run the simulation
    sim.run()
    logger.info('Run done')
    # finish simulation, compute stats
    wrapup()
    logger.info("That's all folks!")
