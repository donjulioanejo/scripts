#!/usr/bin/env python
#
# Nagios plugin for Hazelcast monitoring
# Example usage:
#
# python hazelcast_monitor.py -H mancenter.contoso.local:443 -e prod -m cluster_health
# python hazelcast_monitor.py -H mancenter.contoso.local:443 -e prod -m memory
# python hazelcast_monitor.py -H mancenter.contoso.local:443 -e prod -m queue_sizes
# python hazelcast_monitor.py -H mancenter.contoso.local:443 -e prod -m queue_polls
#
# Define thresholds with -w and -c arguments, or change in this script directly.
#

import json
import requests
import argparse
import sys
from urllib3 import logging
logging.captureWarnings(True)

# Define defaults and thresholds
default_mancenter_host = 'localhost:8443'
default_node_count = 3
memory_warning = 18000
memory_critical = 22000
queue_size_warning_threshold = 750000
queue_size_critical_threshold = 900000
exit_normal = []
exit_warning = []
exit_critical = []
exit_unknown = []

# Set up arguments
parser = argparse.ArgumentParser(description='Check Hazelcast cluster statistics.')
parser.add_argument("-H", "--host", type=str,
                    help="FQDN for Mancenter host, i.e. bastion.load.hyperwallet.aws")
parser.add_argument("-n", "--nodes", type=str,
                    help="Expected number of Hazelcast nodes (default - 3)")
parser.add_argument("-z", "--name", type=str,
                    help="Name of individual Hazelcast node being queried")
parser.add_argument("-w", "--warning", type=int,
                    help="Warning threshold")
parser.add_argument("-c", "--critical", type=int,
                    help="Critical threshold")
parser.add_argument("-m", "--check", type=str,
                    help="Specific check.  Options: (cluster_health, memory, queue_sizes, queue_polls)")
parser.add_argument("-e", "--env", type=str,
                    help="Environment (default: dev)")
parser.add_argument("-t", "--ca_trust", type=str,
                    help="Path to CA cert for SSL/TLS verification (will not use SSL verify if not defined)")
args = parser.parse_args()

# Set environment
if args.env:
    env = args.env
else:
    env = 'dev'

# Set SSL/TLS verification
if args.ca_trust:
    ca_trust = args.ca_trust
else:
    ca_trust = False

# Api Error
class ApiError(Exception):
    """An API Error Exception"""

    def __init__(self, status):
        self.status = status

    def __str__(self):
        return "APIError: status={}".format(self.status)


# Get Mancenter host
def get_host():
    host = args.host
    if host:
        return host
    else:
        return default_mancenter_host


# Get expected number of members in cluster
def get_expected_node_count():
    expected_node_count = args.nodes
    if expected_node_count:
        return expected_node_count
    else:
        return default_node_count


# Which check is being run
def get_check():
    return args.check


# Get thresholds
def get_warning_threshold():
    return args.warning


def get_critical_threshold():
    return args.critical


def get_memory_threshold(value):
    if value == 'warning':
        if get_warning_threshold():
            return get_warning_threshold()
        else:
            return memory_warning
    if value == 'critical':
        if get_critical_threshold():
            return get_critical_threshold()
        else:
            return memory_critical


def get_queue_size_threshold(value):
    if value == 'warning':
        if get_warning_threshold():
            return get_warning_threshold()
        else:
            return queue_size_warning_threshold
    if value == 'critical':
        if get_critical_threshold():
            return get_critical_threshold()
        else:
            return queue_size_critical_threshold


def get_node_name():
    return args.name


# Query functions
def rest_query(path):
    full_url = 'https://' + get_host() + path
    return requests.get(full_url,
                        verify=ca_trust)


def get_queues(env):
    return rest_query('/rest/clusters/' + env + '/queues')


def get_queue_information(env, queue_name):
    return rest_query('/rest/clusters/' + env + '/queues/' + queue_name.replace('/','&#47/'))


def get_members(env):
    return rest_query('/rest/clusters/' + env + '/members')


def get_member_information(env, member):
    return rest_query('/rest/clusters/' + env + '/members/' + member)


# Check Member count
def check_node_count(resp):
    count = len(resp.json())
    return count


# Get cluster memory usage
def get_cluster_memory(resp):
    node_mem_usage = {}
    for node in resp.json():
        each_response = get_member_information(env, node)
        issue = json.loads(each_response.content)
        used_memory = issue['usedMemory']
        node_name = issue['name']
        node_mem_usage[node_name] = used_memory
    return node_mem_usage


# Check cluster memory against thresholds
def check_cluster_memory(resp):
    node_mem_usage = get_cluster_memory(resp)
    warning_threshold = get_memory_threshold('warning')
    critical_threshold = get_memory_threshold('critical')

    exit_result = []
    output_string = ''
    for node in node_mem_usage:
        memory_in_mb = node_mem_usage[node] // 1048576
        node_mem_usage[node] = memory_in_mb
        output_string = output_string + node + ': ' + str(memory_in_mb) + 'M, '
    output_string = "Memory utilization: " + output_string
    for node in node_mem_usage:
        if node_mem_usage[node] > critical_threshold:
            exit_result.append('critical')
        elif node_mem_usage[node] > warning_threshold:
            exit_result.append('warning')
        else:
            exit_result.append('normal')

    if 'critical' in exit_result:
        exit_critical.append('CRITICAL: ' + output_string + 'threshold: ' + str(critical_threshold) + 'M')
    elif 'warning' in exit_result:
        exit_warning.append('WARNING: ' + output_string + 'threshold: ' + str(warning_threshold) + 'M')
    elif 'normal' in exit_result:
        exit_normal.append(output_string)
    else:
        exit_unknown.append('Cannot determine heap utilization')


# Get queue sizes
def get_queue_sizes(queues):
    queue_sizes = {}
    for queue_name in queues.json():
        queue_name_resp = get_queue_information(env, queue_name)
        queue_info = json.loads(queue_name_resp.content)
        queue_size = queue_info['ownedItemCount']
        queue_sizes[queue_name] = queue_size
    return queue_sizes


# Get queue poll counts
def get_queue_polls(queues):
    queue_polls = {}
    for queue_name in queues.json():
        queue_name_resp = get_queue_information(env, queue_name)
        queue_info = json.loads(queue_name_resp.content)
        number_of_polls = queue_info['numberOfPolls']
        queue_polls[queue_name] = number_of_polls
    return queue_polls


# Check queue sizes against thresholds
def check_queue_sizes(queues):
    queue_sizes = get_queue_sizes(queues)
    warning_threshold = get_queue_size_threshold('warning')
    critical_threshold = get_queue_size_threshold('critical')

    exit_result = []
    output_string = ''
    for queue_name in queue_sizes:
        if queue_sizes[queue_name] > critical_threshold:
            exit_result.append('critical')
            output_string = output_string + queue_name + ': ' + str(queue_sizes[queue_name]) + ', '
        elif queue_sizes[queue_name] > warning_threshold:
            exit_result.append('warning')
            output_string = output_string + queue_name + ': ' + str(queue_sizes[queue_name]) + ', '
        else:
            exit_result.append('normal')

    if 'critical' in exit_result:
        exit_critical.append('CRITICAL: ' + output_string + 'threshold: ' + str(critical_threshold))
    elif 'warning' in exit_result:
        exit_warning.append('WARNING: ' + output_string + 'threshold: ' + str(warning_threshold))
    elif 'normal' in exit_result:
        exit_normal.append('All queue sizes are below threshold')
    else:
        exit_unknown.append('Cannot determine queue sizes')


# Check queue information for sizes and polls
def check_queue_polls(queues):
    queue_sizes = get_queue_sizes(queues)
    queue_polls = get_queue_polls(queues)

    exit_result = []
    output_string = ''
    for queue_name in queue_sizes:
        if queue_sizes[queue_name] > 0 and queue_polls[queue_name] < 0.5:
            exit_result.append('critical')
            output_string = output_string + queue_name + 'size: ' + str(queue_sizes[queue_name]) + ', ' + 'polls: ' + str(queue_polls[queue_name])
        elif queue_sizes[queue_name] > 0 and queue_polls[queue_name] >= 0.5:
            exit_result.append('normal')
        elif queue_sizes[queue_name] == 0:
            exit_result.append('normal')
        else:
            exit_result.append('unknown')

    if 'critical' in exit_result:
        exit_critical.append('CRITICAL: ' + output_string + 'threshold: ')
    elif 'normal' in exit_result:
        exit_normal.append('All queue size/poll combinations are normal')
    else:
        exit_unknown.append('Cannot determine queue size/poll count information')


# Check if all members are up, critical warning if any down
def check_node_status(resp):
    node_names = resp.json()
    node_name_str = ''
    node_count = int(check_node_count(resp))
    expected_node_count = int(get_expected_node_count())
    for name in node_names:
        node_name_str = node_name_str + name + ' '
    if node_count < expected_node_count:
        exit_str = "CRITICAL: %s nodes are up (%s expected). Alive cluster members: %s" % (node_count, expected_node_count, node_name_str)
        exit_critical.append(exit_str)
    else:
        exit_str = "All %s nodes are up (%s expected). Cluster members: %s" % (node_count, expected_node_count, node_name_str)
        exit_normal.append(exit_str)


# Final system exit function that exit with specified code
def system_exit():
    if len(exit_critical) > 0:
        for i in exit_critical:
            print i
            sys.exit(2)
    elif len(exit_warning) > 0:
        for i in exit_warning:
            print i
            sys.exit(1)
    elif len(exit_unknown) > 0:
        for i in exit_unknown:
            print(i)
            sys.exit(3)
    elif len(exit_normal) > 0:
        for i in exit_normal:
            print(i)
            sys.exit(0)


def main():
    resp = get_members(env)
    if resp.status_code != 200:
        raise ApiError('GET /members/ {}'.format(resp.status_code))
    queues = get_queues(env)
    if queues.status_code != 200:
        raise ApiError('GET /queues/ {}'.format(queues.status_code))

    check = get_check()
    # print 'Currently running check: ' + check
    if check == 'cluster_health':
        check_node_status(resp)
    elif check == 'memory':
        check_cluster_memory(resp)
    elif check == 'queue_sizes':
        check_queue_sizes(queues)
    elif check == 'queue_polls':
        check_queue_polls(queues)
    else:
        print "No check specified.  Please use -m or --check argument to specify a Nagios check."

    # Exit when done checking and provide exit code
    system_exit()


if __name__ == "__main__":
    main()
