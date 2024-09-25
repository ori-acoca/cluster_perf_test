#!/usr/bin/python3

import os
import sys
from tabulate import tabulate
import inquirer
import paramiko
import time
from colorama import Fore, Style


# Function to print banners
def banner(banner_name):
    banner_map = {
        "welcome": "Network Stress Test",
        "dependency_check": "Checking dependencies across cluster nodes",
        "cleanup": "Cleaning UP leftovers from previous tests",
        "results": "Results"
    }
    print(f"\n{Fore.GREEN}============================================================")
    print(f"{Fore.GREEN}       {banner_map[banner_name]}")
    print(f"{Fore.GREEN}============================================================{Style.RESET_ALL}" + "\n")


# Function to print start of testing banner
def banner_start_testing(link_layer, metric_to_test):
    print(f"\n{Fore.GREEN}============================================================")
    print(f"{Fore.GREEN}       Testing {metric_to_test} all-to-all for {link_layer}")
    print(f"{Fore.GREEN}============================================================{Style.RESET_ALL}" + "\n")


# Get creds from user and define getter methods
class Credentials:
    def __init__(self):
        self._username = input("Enter the username you SSH with: \n")
        print()
        self._key_name = input("Enter your SSH key name: \n")
        print()

    @property
    def username(self):
        return self._username

    @property
    def key_name(self):
        return self._key_name


# Function for executing commands on remote nodes
def execute_on_remote_nodes(host, command, creds, suppress_output=True):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            hostname=host,
            username=creds.username,
            key_filename=os.path.join(os.path.expanduser('~'), ".ssh", creds.key_name)
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


# Function to clean up test leftovers from nodes
def cleanup_leftovers(nodes: list, creds):
    for node in nodes:
        execute_on_remote_nodes(node, "lsof -n -i :18515 | awk '{print $2}' | grep -v PID | xargs kill -9", creds,
                                suppress_output=True)
        execute_on_remote_nodes(node, "lsof -n -i :5001 | awk '{print $2}' | grep -v PID | xargs kill -9", creds,
                                suppress_output=True)


# Function to read node list from a file
def read_node_list(link_layer):
    file_mapping = {
        "Ethernet": "ethernet_ips.txt",
        "InfiniBand": "infiniband_ips.txt"
    }
    if link_layer not in file_mapping:
        raise Exception("Unsupported link layer")
    try:
        with open(file_mapping[link_layer], 'r') as f:
            nodes = [node.strip() for node in f.readlines() if node.strip()]
            return nodes
    except FileNotFoundError:
        print(f"{file_mapping[link_layer]} wasn't found, please check")
        sys.exit()


# Construct server-side command based on link layer and metric
def construct_server_command(link_layer, metric_to_test, server):
    open_server = None

    if link_layer == "Ethernet" and metric_to_test == "Bandwidth":
        open_server = f"iperf -s '{server}' -t 5"
    elif link_layer == "Ethernet" and metric_to_test == "Latency":
        open_server = f"iperf -s '{server}' -t 5"

    elif link_layer == "InfiniBand" and metric_to_test == "Bandwidth":
        open_server = f"ib_send_bw -D5 --report_gbits"
    elif link_layer == "InfiniBand" and metric_to_test == "Latency":
        open_server = f"ib_send_lat -s '{server}' -D5"
    return open_server


# Setup server-side
def run_server(link_layer, metric_to_test, server, creds):
    open_server = construct_server_command(link_layer, metric_to_test, server)
    execute_on_remote_nodes(server, open_server, creds, suppress_output=True)


# Construct client-side command based on link layer and metric
def construct_client_command(link_layer, metric_to_test, server):
    open_client = None

    if link_layer == "Ethernet" and metric_to_test == "Bandwidth":
        open_client = f"iperf -c {server} -P 32 -t 5 -f g | grep SUM | awk '{{print $6}}'"
    elif link_layer == "Ethernet" and metric_to_test == "Latency":
        open_client = f"iperf -c {server} -P 32 -t 5 -f g | grep SUM | awk '{{print $6}}'"

    elif link_layer == "InfiniBand" and metric_to_test == "Bandwidth":
        open_client = f"ib_send_bw \'{server}\' -D5 --output bandwidth --report_gbits -F | awk \'{{printf \"%.2f\\n\", $1}}\'"
    elif link_layer == "InfiniBand" and metric_to_test == "Latency":
        open_client = f"ib_send_lat '{server}' -D5"

    return open_client


# Run client-side
def run_client(link_layer, metric_to_test, client, server, creds):
    open_client = construct_client_command(link_layer, metric_to_test, server)
    print(server + " <===> " + client)
    measured_perf = round(float(execute_on_remote_nodes(client, open_client, creds, suppress_output=False)), )
    return measured_perf


# Run all-to-all test
def all_to_all(link_layer, metric_to_test, node_list: list, creds):
    banner_start_testing(link_layer, metric_to_test)
    results = {}

    for server in node_list:
        print('\n' + "###### " + server + " ######")
        cleanup_leftovers(nodes=[server], creds=creds)
        run_server(link_layer, metric_to_test, server, creds)
        time.sleep(0.2)
        results[server] = {}

        for client in node_list:
            cleanup_leftovers(nodes=[client], creds=creds)

            run_server(link_layer, metric_to_test, server, creds)
            if client != server:
                result = run_client(link_layer, metric_to_test, client, server, creds)
                results[server][client] = result
                time.sleep(0.2)

    return results


# Tabulate results in a table
def tabulate_results(results):
    print(tabulate(results, headers=["Server IP", "Throughput (Gbits/sec)"]))


# Calculate average per server
def calc_avg(results):
    overall_avg_per_server = {}

    for server in results:
        avg_sum = 0.0
        client_count = 0

        for client in results[server]:
            avg_sum += (results[server][client])
            client_count += 1

        overall_avg_per_server[server] = round(avg_sum / client_count if client_count > 0 else 0.0, 2)

    return overall_avg_per_server


# Sort results
def sort_results(overall_avg_per_server):
    # Sort the servers based on overall average performance in descending order
    sorted_avg_per_server = dict(sorted(overall_avg_per_server.items(), key=lambda item: item[1], reverse=True))
    return sorted_avg_per_server


# Format data for tabulate
def format_data_for_tabulate(sorted_avg_per_server):
    formatted_results = [[server, throughput] for server, throughput in sorted_avg_per_server.items()]
    return formatted_results


# Get link layer from user
def get_link_layer():
    # Gather network info from user
    questions = [
        inquirer.List(
            'linklayer',
            message="Layer2 protocol ?",
            choices=['Ethernet', 'InfiniBand'],
        ),
    ]
    answer = inquirer.prompt(questions)
    link_layer = answer['linklayer']
    return link_layer


# Get metric to test from user
def get_metric_to_test():
    # Gather network info from user
    questions = [
        inquirer.List(
            'metric',
            message="What metric do you want to test ?",
            choices=['Bandwidth', 'Latency'],
        ),
    ]
    answer = inquirer.prompt(questions)
    metric = answer['metric']
    return metric


# Check if required tools are installed on the node
def does_ib_send_bw_installed(node, creds):
    run_server("InfiniBand", "Bandwidth", node, creds)
    return "LISTEN" in execute_on_remote_nodes(node, "ss -tulpn | grep ib_send_bw", creds, suppress_output=False)


def does_ib_send_lat_installed(node, creds):
    run_server("InfiniBand", "Latency", node, creds)
    return "LISTEN" in execute_on_remote_nodes(node, "ss -tulpn | grep ib_send_lat", creds, suppress_output=False)


def does_iperf_installed(node, creds):
    run_server("Ethernet", "Bandwidth", node, creds)
    return "LISTEN" in execute_on_remote_nodes(node, "ss -tulpn | grep iperf", creds, suppress_output=False)


# Compile a list of qualified nodes for the test based on link layer, metric, and required packages
def node_qualification(node_list, link_layer, metric_to_test, creds):
    qualified_nodes = []
    for node in node_list:
        if link_layer == "Ethernet" and metric_to_test == "Bandwidth" and does_iperf_installed(node, creds):
            qualified_nodes.append(node)
        elif link_layer == "Ethernet" and metric_to_test == "Latency" and does_iperf_installed(node, creds):
            qualified_nodes.append(node)
        elif link_layer == "InfiniBand" and metric_to_test == "Bandwidth" and does_ib_send_bw_installed(node, creds):
            qualified_nodes.append(node)
        elif link_layer == "InfiniBand" and metric_to_test == "Latency" and does_ib_send_lat_installed(node, creds):
            qualified_nodes.append(node)
        else:
            print(f"Skipping {node} - is missing required tools or is broken")

    return qualified_nodes


# Main function
def main():
    banner("welcome")
    link_layer = get_link_layer()
    metric_to_test = get_metric_to_test()
    creds = Credentials()
    nodes = read_node_list(link_layer)
    banner("cleanup")
    cleanup_leftovers(nodes=nodes, creds=creds)
    banner("dependency_check")
    qualified_nodes = node_qualification(nodes, link_layer, metric_to_test, creds)
    cleanup_leftovers(nodes=nodes, creds=creds)
    results = all_to_all(link_layer=link_layer, metric_to_test=metric_to_test, node_list=qualified_nodes, creds=creds)
    overall_avg_per_server = calc_avg(results)
    banner("results")
    sorted_results = sort_results(overall_avg_per_server)
    formatted_results = format_data_for_tabulate(sorted_results)
    tabulate_results(formatted_results)
    print("")
    print("")
    banner("cleanup")
    cleanup_leftovers(nodes=nodes, creds=creds)
    print("")
    print("             <<<< Done >>>>                      ")
    print()


if __name__ == '__main__':
    main()
