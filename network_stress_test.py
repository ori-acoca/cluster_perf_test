#!/usr/bin/python3

import inquirer
import paramiko
import time

# testtttttt
# Function to execute commands on remote server
def execute_on_remote_nodes(host, username, password, command, supress_output=True):
    client = paramiko.client.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=username, password=password)
    _stdin, _stdout, _stderr = client.exec_command(command)

    if not supress_output:
        return _stdout.read().decode()

    client.close()


# Function to clean-up tests leftovers form nodes
def cleanup_leftovers(username: str, password: str, nodes: list):
    for node in nodes:
        cleanup_command = "pkill -f 'iperf'; pkill -f 'ib_write_bw', pkill -f 'ib_write_lat'"
        print("Cleaning leftovers from previous tests")
        execute_on_remote_nodes(node, username, password, cleanup_command, supress_output=True)


def read_node_list():
    with open('ethernet_ips.txt', 'r') as f:
        nodes = [node.strip() for node in f.readlines()]
        return nodes


def all_to_all(link_layer, node_list: list, username: str, password: str):
    results = {}

    for server in node_list:

        if link_layer == "Ethernet":
            open_server = f"iperf3 -s '{server}' --format G"
        elif link_layer == "InfiniBand":
            open_server = f"ib_write_bw -s '{server}' --report_gbits"
        else:
            raise Exception('Not relevant')

        print("###### " + server + " ######")
        execute_on_remote_nodes(server, username, password, open_server, supress_output=True)

        results[server] = {}

        for client in node_list:
            if client != server:

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
                    raise Exception('Not relevant')

                print(server + " <===> " + client)
                measured_perf = execute_on_remote_nodes(server, username, password, open_client, supress_output=False)

                lines = measured_perf.splitlines()

                if link_layer == "Ethernet":
                    results[server][client] = {}

                    line_pointer = 0

                    for line in lines:

                        if line_pointer == 0:
                            results[server][client]['tx'] = float(line)
                            line_pointer += 1

                        if line_pointer == 1:
                            results[server][client]['rx'] = float(line)

                    results[server][client]['avg'] = float(
                        (float(results[server][client]['rx']) + float(results[server][client]['tx'])) / 2)

                time.sleep(0.1)

    # Calculate the average of averages per server
    overall_avg_per_server = {}

    for server in results:
        avg_sum = 0.0
        client_count = 0

        for client in results[server]:
            avg_sum += results[server][client]['avg']
            client_count += 1

        overall_avg_per_server[server] = avg_sum / client_count

    # Sort the servers based on overall average performance in descending order
    sorted_avg_per_server = dict(sorted(overall_avg_per_server.items(), key=lambda item: item[1], reverse=True))

    # Print the sorted overall average per server
    print("\nOverall Average per Server (Sorted):")
    for server, avg in sorted_avg_per_server.items():
        print(f"{server}:  {avg:.2f} Gbits/sec")


def user_input():
    username = input("Please type the username for the cluster nodes \n")
    password = input("Please type the password for the cluster nodes \n")

    return username, password


def main():
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

    username, password = user_input()

    nodes = read_node_list()
    cleanup_leftovers(username=username, password=password, nodes=nodes)
    all_to_all(link_layer=link_layer, node_list=nodes, username=username, password=password)


if __name__ == '__main__':
    main()
