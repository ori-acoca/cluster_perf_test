#!/usr/bin/python3

import inquirer
import paramiko
import time


# Function to execute commands on remote server
def execute_on_remote_nodes(host, username, password, command, suppress_output=True):
    client = paramiko.client.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=username, password=password)
    _stdin, _stdout, _stderr = client.exec_command(command)

    if not suppress_output:
        output = _stdout.read().decode()
        client.close()
        return output

    client.close()


# Function to clean-up tests leftovers form nodes
def cleanup_leftovers(username: str, password: str, nodes: list):
    cleanup_command = "pkill -f 'iperf'; pkill -f 'ib_write_bw', pkill -f 'ib_write_lat'"
    print("Cleaning leftovers from previous tests")
    for node in nodes:
        execute_on_remote_nodes(node, username, password, cleanup_command, suppress_output=True)


# Function to read node list from a file
def read_node_list():
    with open('ethernet_ips.txt', 'r') as f:
        nodes = [node.strip() for node in f.readlines()]
    return nodes


# Function to set up the server for testing
def setup_server(link_layer, server, username, password):
    if link_layer == "Ethernet":
        open_server = f"iperf3 -s '{server}' --format G"
    elif link_layer == "InfiniBand":
        open_server = f"ib_write_bw -s '{server}' --report_gbits"
    else:
        raise Exception('Unsupported link layer')

    print("###### " + server + " ######")
    execute_on_remote_nodes(server, username, password, open_server, suppress_output=True)


# Function to run performance test from client to server
def run_client_test(link_layer, client, server, username, password):
    if link_layer == "Ethernet":
        open_client = (
            f"iperf3 -c {server} -P 8 -t 1 | "
            f"grep SUM | "
            f"egrep 'sender|receiver' | "
            f"awk '{{for(i=1;i<=NF;i++) if ($i ~ /bits\\/sec$/) print $(i-1) \" \" $i}}' | "
            f"awk '{{print $1}}'"
        )
    elif link_layer == "InfiniBand":
        open_client = f"ib_write_bw '{server}' --report_gbits"
    else:
        raise Exception('Unsupported link layer')

    print(server + " <===> " + client)
    measured_perf = execute_on_remote_nodes(client, username, password, open_client, suppress_output=False)
    return parse_performance_output(link_layer, measured_perf)


# Function to parse performance output
def parse_performance_output(link_layer, measured_perf):
    lines = measured_perf.splitlines()
    result = {}

    if link_layer == "Ethernet":
        if len(lines) >= 2:
            result['tx'] = float(lines[0])
            result['rx'] = float(lines[1])
            result['avg'] = (result['tx'] + result['rx']) / 2

    return result


# Function to perform all-to-all performance tests
def all_to_all(link_layer, node_list: list, username: str, password: str):
    results = {}

    for server in node_list:
        setup_server(link_layer, server, username, password)
        results[server] = {}

        for client in node_list:
            if client != server:
                result = run_client_test(link_layer, client, server, username, password)
                results[server][client] = result

                time.sleep(0.1)
    return results


# Calculate the average of averages per server
def calc_avg(results):
    overall_avg_per_server = {}

    for server in results:
        avg_sum = 0.0
        client_count = 0

        for client in results[server]:
            avg_sum += results[server][client]['avg']
            client_count += 1

        overall_avg_per_server[server] = avg_sum / client_count

    return overall_avg_per_server


def sort_results(overall_avg_per_server):
    # Sort the servers based on overall average performance in descending order
    sorted_avg_per_server = dict(sorted(overall_avg_per_server.items(), key=lambda item: item[1], reverse=True))

    # Print the sorted overall average per server
    print("\nOverall Average per Server (Sorted):")
    for server, avg in sorted_avg_per_server.items():
        print(f"{server}:  {avg:.2f} Gbits/sec")


def get_creds():
    username = input("Please type the username for the cluster nodes \n")
    password = input("Please type the password for the cluster nodes \n")

    return username, password


def get_link_layer():
    # Gather network info from user
    questions = [
        inquirer.List(
            'linklayer',
            message="Layer2 protocol - Ethernet or InfiniBand ?",
            choices=['Ethernet', 'InfiniBand'],
        ),
    ]
    answer = inquirer.prompt(questions)
    link_layer = answer['linklayer']
    return link_layer


def main():
    username, password = get_creds()
    link_layer = get_link_layer()
    nodes = read_node_list()
    cleanup_leftovers(username=username, password=password, nodes=nodes)
    results = all_to_all(link_layer=link_layer, node_list=nodes, username=username, password=password)
    overall_avg_per_server = calc_avg(results)
    sort_results(overall_avg_per_server)


if __name__ == '__main__':
    main()
