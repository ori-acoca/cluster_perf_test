#!/usr/bin/python3

import os
import sys

from tabulate import tabulate
import paramiko
import time
from colorama import Fore, Style
import logging
import argparse


logging.basicConfig(
    level=logging.WARNING,  # log level
    format='%(asctime)s - %(levelname)s - %(message)s'  # log message format
)
logger = logging.getLogger(__name__)


def banner(banner_name):
    """
    Function to print banners

    :param banner_name: name of the banner to print
    """
    banner_map = {
        "welcome": "Network Stress Test",
        "dependency_check": "Checking dependencies across cluster nodes",
        "cleanup": "Cleaning UP leftovers from previous tests",
        "results": "Results",
        "connection": "Checking connection to node",
        "done": "Done"
    }
    print(f"\n{Fore.GREEN}============================================================================")
    (print(f"{Fore.GREEN}{banner_map[banner_name]}"))
    print(
        f"{Fore.GREEN}============================================================================{Style.RESET_ALL}" + "\n")


def check_connection(nodes: list, user, key):
    responsive_nodes = []
    unresponsive_nodes = []
    for node in nodes:
        try:
            uptime = execute_on_remote_nodes(node, "uptime", user, key, suppress_output=False)
            if uptime:
                print(f"Connection to {node} is successful")
                responsive_nodes.append(node)
        except Exception as e:
            logger.error(f"Connection to {node} failed with error: {e}")
            unresponsive_nodes.append(node)
            continue
    return responsive_nodes, unresponsive_nodes


def validate_private_key(key):
    """
    Function to validate that the private key is in the correct location and is indeed a private key

    :param key: key's name
    :return: pass so the script can continue
    sys.exit() if the key is not found or not valid to stop the script
    """
    try:
        with open(f"/root/.ssh/{key}") as f:
            if 'PRIVATE KEY' in f.read():
                pass
    except FileNotFoundError:
        logger.error(f"Private key {key} wasn't found in /root/.ssh/")
        sys.exit()


def banner_start_testing(link_layer, metric_to_test):
    """
    Function to print start of testing banner

    :param link_layer:
    :param metric_to_test:
    """
    print(f"\n{Fore.GREEN}===========================================================================")
    print(f"{Fore.GREEN}Testing {metric_to_test} all-to-all for {link_layer}")
    print(
        f"{Fore.GREEN}============================================================================{Style.RESET_ALL}" + "\n")


def get_args():
    """
    Function to parse command line arguments

    :return: args
    """
    parser = argparse.ArgumentParser(description='Network Stress Test')
    parser.add_argument('--linklayer', type=str, help='Layer2 protocol', choices=['ib', 'eth'], required=True)
    parser.add_argument('--metric', type=str, help='Metric to test', choices=['bw', 'lat'], required=True)
    parser.add_argument('--user', type=str, help='SSH username', required=True)
    parser.add_argument('--key', type=str, help='SSH key name (must be in /root/.ssh/)', required=True)
    parser.add_argument('--nodes', type=str, help='file contains a list of IPs of the test', required=True)
    args = parser.parse_args()
    return args


def write_to_file(data_to_write: list, file_name: str):
    """
    Function to write data to a file

    :param data_to_write: a list of data to write to a file
    :param file_name: name of the file to write to
    """

    try:
        with open(fr'./{file_name}', 'w') as f:
            f.write('\n'.join(data_to_write))
    except Exception as e:
        logger.error(f"Error: can't write log to file {file_name} - {e}")


def validate_nic_type(node, link_layer, user, key):
    """
    Function to validate that the NIC link_layer or of the server is indeed as declared by the user

    :param node:
    :param link_layer:
    :param user:
    :param key:
    :return: Boolean value indicating if the NIC link_layer is as declared by the user
    """
    command = f"ip route show | grep {node} | awk '{{print $3}}' | xargs ip link show | grep link | awk '{{print $1}}'"

    try:
        actual_link_layer = execute_on_remote_nodes(host=node, command=command, user=user, key=key,
                                                    suppress_output=False)
        if link_layer in actual_link_layer:
            return True
        elif link_layer not in actual_link_layer:
            logger.error(f"NIC with IP {node} is {actual_link_layer}, {link_layer} was expected")
            return False
        else:
            logger.info(f"link_layer on {node} can't be identified - Skipping")
            return False
    except Exception as e:
        logger.error(f"Error: {e}")


def execute_on_remote_nodes(host, command, user, key, suppress_output=True):
    """
    Function for executing commands on remote nodes

    :param host:
    :param command:
    :param user:
    :param key:
    :param suppress_output:
    :return: output from the command executed on the remote node (if suppress_output is False)
    """
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            hostname=host,
            username=user,
            key_filename=os.path.join(os.path.expanduser('~'), ".ssh", key)
        )
        _stdin, _stdout, _stderr = ssh.exec_command(command)
        if not suppress_output:
            output = _stdout.read().decode()
            ssh.close()
            return output
    except paramiko.SSHException as e:
        print(f"SSH error: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()
    return ""


def cleanup_leftovers(nodes: list, user, key, supress_notice=True):
    """
    Function to cleanup leftovers from previous tests

    :param nodes: list of nodes to executed a cleanup on
    :param user: username to use for SSH
    :param key: SSH key to use for authentication
    :param supress_notice: Boolean value to suppress cleanup notice
    """
    for node in nodes:
        execute_on_remote_nodes(node, "lsof -n -i :18515 | awk '{print $2}' | grep -v PID | xargs kill -9", user,
                                key,
                                suppress_output=True)
        execute_on_remote_nodes(node, "lsof -n -i :5001 | awk '{print $2}' | grep -v PID | xargs kill -9", user,
                                key,
                                suppress_output=True)
        if not supress_notice:
            print(f"Cleaning up leftovers on {node}")


def read_node_list(file):
    """
    Function to read node list from a file

    :param file: a file containing a list of nodes in-band IP addresses
    :return: nodes list
    """
    try:
        with open(file, 'r') as f:
            nodes = [node.strip() for node in f.readlines() if node.strip()]
            return nodes
    except FileNotFoundError:
        print("node list file wasn't found, please check")
        sys.exit()


def construct_server_command(link_layer, metric_to_test, server):
    """
    Function to construct server-side command based on link layer and metric

    :param link_layer: ib (Infiniband) or eth (Ethernet)
    :param metric_to_test: bw (bandwidth) or lat (latency)
    :param server: server IP address
    :return: open-server - command to run on the server
    """
    open_server = None

    if link_layer == "eth" and metric_to_test == "bw":
        open_server = f"iperf -s '{server}' -t 5"
    elif link_layer == "eth" and metric_to_test == "lat":
        open_server = f"iperf -s '{server}' -t 5"

    elif link_layer == "ib" and metric_to_test == "bw":
        open_server = f"ib_send_bw -D5 --report_gbits"
    elif link_layer == "ib" and metric_to_test == "lat":
        open_server = f"ib_send_lat -s '{server}' -D5"
    return open_server


def run_server(link_layer, metric_to_test, server, user, key):
    """
    Function to setup server-side, based on link layer and metric

    :param link_layer: ib (Infiniband) or eth (Ethernet)
    :param metric_to_test: bw (bandwidth) or lat (latency)
    :param server: server IP address
    :param user: username to use for SSH
    :param key: SSH key to use for authentication
    :return: None
    """
    try:
        open_server = construct_server_command(link_layer, metric_to_test, server)
        execute_on_remote_nodes(server, open_server, user, key, suppress_output=True)
    except Exception as e:
        logger.error(f"Error: {e}")


def construct_client_command(link_layer, metric_to_test, server):
    """
    Function to construct client-side command based on link layer and metric

    :param link_layer: ib (Infiniband) or eth (Ethernet)
    :param metric_to_test: bw (bandwidth) or lat (latency)
    :param server: server IP address
    :return: open_client - command to run on the client
    """
    open_client = None

    if link_layer == "eth" and metric_to_test == "bw":
        open_client = f"iperf -c {server} -P 32 -t 5 -f g | grep SUM | awk '{{print $6}}'"
    elif link_layer == "eth" and metric_to_test == "lat":
        open_client = f"iperf -c {server} -P 32 -t 5 -f g | grep SUM | awk '{{print $6}}'"

    elif link_layer == "ib" and metric_to_test == "bw":
        open_client = f"ib_send_bw \'{server}\' -D5 --output bandwidth --report_gbits -F | awk \'{{printf \"%.2f\\n\", $1}}\'"
    elif link_layer == "ib" and metric_to_test == "lat":
        open_client = f"ib_send_lat '{server}' -D5"

    return open_client


def run_client(link_layer, metric_to_test, client, server, user, key):
    """
    Function to run client-side, based on link layer and metric

    :param link_layer: ib (Infiniband) or eth (Ethernet)
    :param metric_to_test: bw (bandwidth) or lat (latency)
    :param client: client IP address
    :param server: server IP address
    :param user: username to use for SSH
    :param key: SSH key to use for authentication
    :return: measured_perf - performance measured on the client during the test
    """
    try:
        open_client = construct_client_command(link_layer, metric_to_test, server)
        print(server + " <===> " + client)
        measured_perf = round(float(execute_on_remote_nodes(client, open_client, user, key, suppress_output=False)), )
        return measured_perf
    except Exception as e:
        logger.error(f"Error: {e}")


def all_to_all(link_layer, metric_to_test, node_list: list, user, key):
    """
    Function to run all-to-all test

    :param link_layer:  ib (Infiniband) or eth (Ethernet)
    :param metric_to_test: bw (bandwidth) or lat (latency)
    :param node_list: list of nodes to run the test on
    :param user: username to use for SSH
    :param key: SSH key to use for authentication
    :return: Nested dictionary containing results of each node with all other nodes
    """
    banner_start_testing(link_layer, metric_to_test)
    results = {}

    for server in node_list:
        print('\n' + "###### " + server + " ######")
        cleanup_leftovers(nodes=[server], user=user, key=key, supress_notice=True)
        run_server(link_layer, metric_to_test, server, user, key)
        time.sleep(0.2)
        results[server] = {}

        for client in node_list:
            cleanup_leftovers(nodes=[client], user=user, key=key)

            run_server(link_layer, metric_to_test, server, user, key)
            if client != server:
                result = run_client(link_layer, metric_to_test, client, server, user, key)
                results[server][client] = result
                time.sleep(0.2)

    return results


def calc_avg(results):
    """
    Function to calculate average per server

    :param results: received from all-to-all test
    :return: A dictionary containing overall average performance per server
    """
    overall_avg_per_server = {}

    for server in results:
        avg_sum = 0.0
        client_count = 0

        for client in results[server]:
            avg_sum += (results[server][client])
            client_count += 1

        overall_avg_per_server[server] = round(avg_sum / client_count if client_count > 0 else 0.0, 2)

    return overall_avg_per_server


def sort_results(overall_avg_per_server):
    """
    Function to sort results based on overall average performance in descending order

    :param overall_avg_per_server: Dictionary containing overall average performance per server
    :return: sorted_avg_per_server - sorted results
    """
    sorted_avg_per_server = dict(sorted(overall_avg_per_server.items(), key=lambda item: item[1], reverse=True))
    return sorted_avg_per_server


def tabulate_results(sorted_avg_per_server):
    """
    Function to format and tabulate results in a table

    :param sorted_avg_per_server: sorted results
    :return: print tabulated results
    """
    formatted_results = [[server, throughput] for server, throughput in sorted_avg_per_server.items()]
    print(tabulate(formatted_results, headers=["Server IP", "Throughput (Gbits/sec)"]))


def does_ib_send_bw_installed(node, user, key):
    """
    Function to check if ib_send_bw is installed on the node

    :param node: server we want to check
    :param user: username to use for SSH
    :param key: SSH key to use for authentication
    :return: Boolean value indicating if ib_send_bw is installed on the node
    """
    try:
        run_server("ib", "bw", node, user, key)
        return "LISTEN" in execute_on_remote_nodes(node, "ss -tulpn | grep ib_send_bw", user, key,
                                                   suppress_output=False)
    except Exception as e:
        logger.error(f"Error: {e}")
        logger.error(f"can't evaluate dependencies for {node}")
        return False


def does_ib_send_lat_installed(node, user, key):
    """
    Function to check if ib_send_lat is installed on the node

    :param node: server we want to check
    :param user: username to use for SSH
    :param key: SSH key to use for authentication
    :return: Boolean value indicating if ib_send_lat is installed on the node
    """
    try:
        run_server("ib", "lat", node, user, key)
        return "LISTEN" in execute_on_remote_nodes(node, "ss -tulpn | grep ib_send_lat", user, key,
                                                   suppress_output=False)
    except Exception as e:
        logger.error(f"Error: {e}")
        logger.error(f"can't evaluate dependencies for {node}")
        return False


def does_iperf_installed(node, user, key):
    """
    Function to check if iperf is installed on the node

    :param node: server we want to check
    :param user: username to use for SSH
    :param key: SSH key to use for authentication
    :return: Boolean value indicating if iperf is installed on the node
    """
    try:
        run_server("eth", "bw", node, user, key)
        return "LISTEN" in execute_on_remote_nodes(node, "ss -tulpn | grep iperf", user, key, suppress_output=False)
    except Exception as e:
        logger.error(f"Error: {e}")
        logger.error(f"can't evaluate dependencies for {node}")
        return False


def node_qualification(node_list, link_layer, metric_to_test, user, key):
    """
    Function to compile a list of qualified nodes for the test based on required packages

    :param node_list: A list of nodes to be tested
    :param link_layer: ib (Infiniband) or eth (Ethernet); based on the link layer, the required tools will be checked
    :param metric_to_test: bw (bandwidth) or lat (latency); based on the metric, the required tools will be checked
    :param user: username to use for SSH
    :param key: SSH key to use for authentication
    :return: qualified_nodes - list of nodes that are qualified for the test
    """
    qualified_nodes = []
    for node in node_list:
        if validate_nic_type(node, link_layer, user, key):
            if link_layer == "eth" and does_iperf_installed(node, user, key):
                qualified_nodes.append(node)
                print(f"Adding {node} to the list of qualified nodes")
            elif link_layer == "ib":
                if metric_to_test == "bw" and does_ib_send_bw_installed(node, user, key):
                    qualified_nodes.append(node)
                    print(f"Adding {node} to the list of qualified nodes")
                elif metric_to_test == "lat" and does_ib_send_lat_installed(node, user, key):
                    qualified_nodes.append(node)
                    print(f"Adding {node} to the list of qualified nodes")
            else:
                print(f"Skipping {node} - is missing required tools or is broken")
        else:
            print("Link_layer declared for the NIC isn't as the actual NIC link_layer on the server")

    return qualified_nodes


def main():
    """
    Main function
    """
    banner("welcome")
    banner("connection")
    args = get_args()
    nodes = read_node_list(args.nodes)
    validate_private_key(args.key)
    responsive_nodes, unresponsive_nodes = check_connection(nodes, args.user, args.key)
    write_to_file(data_to_write=responsive_nodes, file_name="responsive_nodes.txt")
    write_to_file(data_to_write=unresponsive_nodes, file_name="unresponsive_nodes.txt")
    banner("cleanup")
    cleanup_leftovers(nodes=responsive_nodes, user=args.user, key=args.key, supress_notice=False)
    banner("dependency_check")
    qualified_nodes = node_qualification(responsive_nodes, args.linklayer, args.metric, args.user, args.key)
    results = all_to_all(link_layer=args.linklayer, metric_to_test=args.metric, node_list=qualified_nodes,
                         user=args.user, key=args.key)
    overall_avg_per_server = calc_avg(results)
    banner("results")
    sorted_results = sort_results(overall_avg_per_server)
    cleanup_leftovers(nodes=responsive_nodes, user=args.user, key=args.key, supress_notice=False)
    tabulate_results(sorted_results)
    print("")
    print("")
    banner("cleanup")
    banner("done")


if __name__ == '__main__':
    main()
