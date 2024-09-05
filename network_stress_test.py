#!/usr/bin/python3
import os
import sys
import inquirer
import paramiko
import time


class Credentials:
    def __init__(self):
        # Initialize the object with user input for two values
        self._username = input("Enter the username you are SSH with: \n")
        self._key_name = input("\nEnter your SSH key name: \n")

    @property
    def username(self):
        # Getter method for retrieving the username
        return self._username

    @property
    def key_name(self):
        # Getter method for retrieving the SSH key name
        return self._key_name


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
    print("\nCleaning leftovers from previous tests")
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


# Function to set up the server for testing
def setup_server(link_layer, server, creds):
    if link_layer == "Ethernet":
        open_server = f"iperf -s '{server}'"
    elif link_layer == "InfiniBand":
        open_server = f"ib_write_bw -s '{server}' --report_gbits"
    else:
        raise Exception('Unsupported link layer')

    print('\n' + "###### " + server + " ######")
    execute_on_remote_nodes(server, open_server, creds, suppress_output=True)


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


# Function to perform all-to-all performance tests
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

    # Print the sorted overall average per server
    print("\nOverall Average per Server (Sorted):")
    for server, avg in sorted_avg_per_server.items():
        print(f"{server}:  {avg:.2f} Gbits/sec")


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
    link_layer = get_link_layer()
    creds = Credentials()
    nodes = read_node_list(link_layer)
    cleanup_leftovers(nodes=nodes, creds=creds)
    results = all_to_all(link_layer=link_layer, node_list=nodes, creds=creds)
    overall_avg_per_server = calc_avg(results)
    sort_results(overall_avg_per_server)
    cleanup_leftovers(nodes=nodes, creds=creds)

if __name__ == '__main__':
    main()
