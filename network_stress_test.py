#!/usr/bin/python3
import os
import sys
from xmlrpc.client import boolean
from tabulate import tabulate
import inquirer
import paramiko
import time
from colorama import Fore, Style


# Banners
def banner_welcome():
    print(f"{Fore.GREEN}============================================================")
    print(f"{Fore.GREEN}                   Network Stress Test")
    print(f"{Fore.GREEN}============================================================{Style.RESET_ALL}")
    print()


def banner_dependency_check():
    print(f"{Fore.GREEN}============================================================")
    print(f"{Fore.GREEN}       Checking dependencies across cluster nodes")
    print(f"{Fore.GREEN}============================================================{Style.RESET_ALL}")
    print()


def banner_cleanup():
    print(f"{Fore.GREEN}============================================================")
    print(f"{Fore.GREEN}       Cleaning UP leftovers from previous tests")
    print(f"{Fore.GREEN}============================================================{Style.RESET_ALL}")
    print()


def banner_ipref():
    print(f"{Fore.GREEN}============================================================")
    print(f"{Fore.GREEN}       Testing iPerf all-to-all")
    print(f"{Fore.GREEN}============================================================{Style.RESET_ALL}")
    print()


def banner_results():
    print()
    print()
    print(f"{Fore.GREEN}============================================================")
    print(f"{Fore.GREEN}       Results")
    print(f"{Fore.GREEN}============================================================{Style.RESET_ALL}")
    print()


# Get creds from user
class Credentials:
    def __init__(self):
        # Initialize the object with user input for two values
        self._username = input("Enter the username you SSH with: \n")
        print()
        self._key_name = input("Enter your SSH key name: \n")
        print()

    @property
    def username(self):
        # Getter method for retrieving the username
        return self._username

    @property
    def key_name(self):
        # Getter method for retrieving the SSH key name
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
            #print(output)
            return output
    except paramiko.SSHException as e:
        print(f"SSH error: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()


# Function to clean up test leftovers from nodes
def cleanup_leftovers(nodes: list, creds):
    cleanup_command = "pkill -f 'iperf'; pkill -f 'ib_write_bw'; pkill -f 'ib_write_lat'"
    banner_cleanup()
    for node in nodes:
        execute_on_remote_nodes(node, cleanup_command, creds, suppress_output=True)


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
            nodes = [node.strip() for node in f.readlines()]
            return nodes
    except FileNotFoundError:
        print(f"{file_mapping[link_layer]} wasn't found, please check")
        sys.exit()


def construct_server_command(link_layer, metric_to_test, server):
    open_server = None

    if link_layer == "Ethernet" and metric_to_test == "Bandwidth":
        open_server = f"iperf -s '{server}'"
    elif link_layer == "Ethernet" and metric_to_test == "Latency":
        open_server = f"iperf -s '{server}'"

    elif link_layer == "InfiniBand" and metric_to_test == "Bandwidth":
        open_server = f"ib_write_bw -s '{server}' --report_gbits"
    elif link_layer == "InfiniBand" and metric_to_test == "Latency":
        open_server = f"ib_write_lat -s '{server}'"

    return open_server


# Setup server-side
def run_server(link_layer, metric_to_test, server, creds):
    open_server = construct_server_command(link_layer, metric_to_test, server)
    print('\n' + "###### " + server + " ######")
    execute_on_remote_nodes(server, open_server, creds, suppress_output=True)


def construct_client_command(link_layer, metric_to_test, server):
    open_client = None

    if link_layer == "Ethernet" and metric_to_test == "Bandwidth":
        open_client = f"iperf -c {server} -P 32 -f g | grep SUM | awk '{{print $6}}'"
    elif link_layer == "Ethernet" and metric_to_test == "Latency":
        open_client = f"iperf -c {server} -P 32 -f g | grep SUM | awk '{{print $6}}'"

    elif link_layer == "InfiniBand" and metric_to_test == "Bandwidth":
        open_client = f"ib_write_bw '{server}' --report_gbits"
    elif link_layer == "InfiniBand" and metric_to_test == "Latency":
        open_client = f"ib_write_bw '{server}' -D 10"

    return open_client


# Setup client-side
def run_client(link_layer, metric_to_test, client, server, creds):
    open_client = construct_client_command(link_layer, metric_to_test, server)
    print(server + " <===> " + client)
    measured_perf = (execute_on_remote_nodes(client, open_client, creds, suppress_output=False))
    measured_perf = float(measured_perf.strip())
    return measured_perf


# Perform all-to-all performance tests
def all_to_all(link_layer, metric_to_test, node_list: list, creds):
    banner_start_testing(link_layer, metric_to_test)
    results = {}

    for server in node_list:
        run_server(link_layer, metric_to_test, server, creds)
        results[server] = {}

        for client in node_list:
            if client != server:
                result = run_client(link_layer, metric_to_test, client, server, creds)
                results[server][client] = result
                time.sleep(0.1)

    return results


def banner_start_testing(link_layer, metric_to_test):
    print(f"{Fore.GREEN}============================================================")
    print(f"{Fore.GREEN}       Testing {metric_to_test} all-to-all for {link_layer}")
    print(f"{Fore.GREEN}============================================================{Style.RESET_ALL}")
    print()


# Tabulate results in a table
def tabulate_results(results):
    print(tabulate(results, headers=["Server IP", "Throughput (Gbits/sec)"]))


# Calculate the average of averages per server
def calc_avg(results):
    overall_avg_per_server = {}

    for server in results:
        avg_sum = 0.0
        client_count = 0

        for client in results[server]:
            avg_sum += (results[server][client])
            client_count += 1

        overall_avg_per_server[server] = avg_sum / client_count if client_count > 0 else 0.0

    return overall_avg_per_server


def sort_results(overall_avg_per_server):
    # Sort the servers based on overall average performance in descending order
    sorted_avg_per_server = dict(sorted(overall_avg_per_server.items(), key=lambda item: item[1], reverse=True))
    return sorted_avg_per_server


def format_data_for_tabulate(sorted_avg_per_server):
    formatted_results = [[server, throughput] for server, throughput in sorted_avg_per_server.items()]
    return formatted_results


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


def init_nodes_attributes_dict(nodes: list):
    nodes_attributes_dict = {}
    for node in nodes:
        nodes_attributes_dict[node] = {
            'ib_write_bw': "",
            'ib_write_lat': "",
            'iperf': "",
        }
    return nodes_attributes_dict


def check_dependencies(nodes_attributes_dict: dict, creds):
    for node, attributes in nodes_attributes_dict.items():
        nodes_attributes_dict[node]["ib_write_bw"] = boolean(does_ib_write_bw_installed(node, creds))
        nodes_attributes_dict[node]["ib_write_lat"] = boolean(does_ib_write_lat_installed(node, creds))
        nodes_attributes_dict[node]["iperf"] = boolean(does_iperf_installed(node, creds))
    return nodes_attributes_dict


def does_ib_write_bw_installed(node, creds):
    check_command = "which ib_write_bw"
    output = execute_on_remote_nodes(node, check_command, creds, suppress_output=False)
    if "ib_write_bw" in output:
        return True
    else:
        return False


def does_ib_write_lat_installed(node, creds):
    check_command = "which ib_write_lat"
    output = execute_on_remote_nodes(node, check_command, creds, suppress_output=False)
    if "ib_write_lat" in output.lower():
        return True
    else:
        return False


def does_iperf_installed(node, creds):
    check_command = "which iperf"
    output = execute_on_remote_nodes(node, check_command, creds, suppress_output=False)
    if "iperf" in output.lower():
        return True
    else:
        return False


def node_qualification(node_dependencies_status, link_layer, metric_to_test):
    qualified_nodes = []
    for node, status in node_dependencies_status.items():

        if link_layer == "Ethernet":
            if metric_to_test == "Bandwidth":
                if status['iperf'] is False:
                    print("Skipping " + node + " - is missing iperf or is broken")
                else:
                    qualified_nodes.append(node)

        if link_layer == "InfiniBand":
            if metric_to_test == "Bandwidth":
                if not ['ib_write_bw']:
                    print("Skipping " + node + " - is missing ib_write_bw or is broken")
                else:
                    qualified_nodes.append(node)

            if metric_to_test == "Latency":
                if not status['ib_write_lat']:
                    print("Skipping " + node + " - is missing ib_write_lat or is broken")
                else:
                    qualified_nodes.append(node)

    return qualified_nodes


def main():
    banner_welcome()
    link_layer = get_link_layer()
    metric_to_test = get_metric_to_test()
    creds = Credentials()
    nodes = read_node_list(link_layer)
    nodes_attributes_dict = init_nodes_attributes_dict(nodes)
    node_dependencies_status = check_dependencies(nodes_attributes_dict, creds)
    banner_dependency_check()
    qualified_nodes = node_qualification(node_dependencies_status, link_layer, metric_to_test)
    cleanup_leftovers(nodes=nodes, creds=creds)
    results = all_to_all(link_layer=link_layer, metric_to_test=metric_to_test, node_list=qualified_nodes, creds=creds)
    overall_avg_per_server = calc_avg(results)
    banner_results()
    sorted_results = sort_results(overall_avg_per_server)
    formatted_results = format_data_for_tabulate(sorted_results)
    tabulate_results(formatted_results)
    print("")
    print("")

    cleanup_leftovers(nodes=qualified_nodes, creds=creds)
    print("")
    print("             <<<< Done >>>>                      ")
    print()

if __name__ == '__main__':
    main()

