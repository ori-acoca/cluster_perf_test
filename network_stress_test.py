#!/usr/bin/python3
import os
import sys
from tabulate import tabulate
import inquirer
import paramiko
import time
from colorama import Fore, Back, Style


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


# Setup server-side to accept connections
def setup_server(link_layer, server, creds):
    if link_layer == "Ethernet":
        open_server = f"iperf -s '{server}'"
    elif link_layer == "InfiniBand":
        open_server = f"ib_write_bw -s '{server}' --report_gbits"
    else:
        raise Exception('Unsupported link layer')

    print('\n' + "###### " + server + " ######")
    execute_on_remote_nodes(server, open_server, creds, suppress_output=True)


# Setup client side to connect to server and collect results
def run_client_test(link_layer, client, server, creds):
    if link_layer == "Ethernet":
        open_client = (
            f"iperf -c {server} -P 32 -f g | grep SUM | awk '{{print $6}}'"
        )
    elif link_layer == "InfiniBand":
        open_client = f"ib_write_bw '{server}' --report_gbits"
    else:
        raise Exception('Unsupported link layer')

    print(server + " <===> " + client)
    measured_perf = execute_on_remote_nodes(client, open_client, creds, suppress_output=False)
    # Remove any trailing whitespace or newline characters from the output
    measured_perf = measured_perf.strip()
    return measured_perf


# Perform all-to-all performance tests
def all_to_all(link_layer, node_list: list, creds):
    results = {}

    for server in node_list:
        setup_server(link_layer, server, creds)
        results[server] = {}

        for client in node_list:
            if client != server:
                result = run_client_test(link_layer, client, server, creds)
                results[server][client] = result
                time.sleep(0.1)
    return results


def tabulate_results(results):
    print(tabulate(results, headers=["Server IP", "Throughput (Gbits/sec)"]))


# Calculate the average of averages per server
def calc_avg(results):
    overall_avg_per_server = {}

    for server in results:
        avg_sum = 0.0
        client_count = 0

        for client in results[server]:
            # Convert the string result to float and strip any extra whitespace or newline characters
            avg_sum += float(results[server][client].strip())
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


def check_dependencies(nodes: list, creds):
    dependency_pass_nodes = []
    dependency_fail_nodes = []

    check_iperf = "if command -v iperf &> /dev/null; then echo 'Pass'; else echo 'Fail'; fi"
    check_perftest = "if command -v ib_write_bw &> /dev/null; then echo 'Pass'; else echo 'Fail'; fi"

    for node in nodes:
        is_iperf_there = execute_on_remote_nodes(node, check_iperf, creds, suppress_output=False)
        is_perftest_there = execute_on_remote_nodes(node, check_perftest, creds, suppress_output=False)

        if "Pass" in is_iperf_there and is_perftest_there:
            dependency_pass_nodes.append(node)
        else:
            dependency_fail_nodes.append(node)

    return dependency_pass_nodes, dependency_fail_nodes


def report_skipped_nodes(dependency_fail_nodes):
    for node in dependency_fail_nodes:
        print("Skipping " + node + " - Missing dependencies")


def main():
    banner_welcome()
    link_layer = get_link_layer()
    creds = Credentials()
    nodes = read_node_list(link_layer)
    dependency_pass_nodes, dependency_fail_nodes = check_dependencies(nodes, creds)
    banner_dependency_check()
    report_skipped_nodes(dependency_fail_nodes)
    cleanup_leftovers(nodes=dependency_pass_nodes, creds=creds)
    banner_ipref()
    results = all_to_all(link_layer=link_layer, node_list=dependency_pass_nodes, creds=creds)
    overall_avg_per_server = calc_avg(results)
    banner_results()
    sorted_results = sort_results(overall_avg_per_server)
    formatted_results = format_data_for_tabulate(sorted_results)
    tabulate_results(formatted_results)
    print("")
    print("")

    cleanup_leftovers(nodes=dependency_pass_nodes, creds=creds)
    print("")
    print("             <<<< Done >>>>                      ")
    print()
if __name__ == '__main__':
    main()
