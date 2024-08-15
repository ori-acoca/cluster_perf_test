#!/usr/bin/python3

import subprocess
import inquirer
import ipaddress
import psutil
import paramiko
import time
import json
import pandas as pd
import seaborn as sns


# Gather network info from user
questions = [
  inquirer.List('linklayer',
                message="Layer2 protocol - Ethernet or InfiniBand ?",
                choices=['Ethernet', 'InfiniBand'],
            ),
]
answer = inquirer.prompt(questions)
linklayer = answer['linklayer']


# Gather nodes credentials
username = input("Please type the username for the cluster nodes \n")
password = input("Please type the password for the cluster nodes \n")


# Function to execute commands on remote server
def execute_on_remote_nodes(host, username, password, command, supress_output=True):
    client = paramiko.client.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=username, password=password)
    _stdin, _stdout,_stderr = client.exec_command(command)

    if supress_output == False:
        return(_stdout.read().decode())

    client.close()



if linklayer == "Ethernet":
    print ("Running tests for Ethernet")

    # Read server list and strip newline characters
    with open('ethernet_ips.txt', 'r') as f:
        nodes = [node.strip() for node in f.readlines()]


    # Cleanup previous tests lefovers form nodes
    for node in nodes:
        cleanup_command = "ps -ef | grep -i iperf | grep -v grep | awk '{print $2}"
        print ("Cleaning orphaned iPerf3 processes")
        execute_on_remote_nodes(node, username, password, cleanup_command, supress_output=True)

    # Create empty dictionary to store test results
    results = {}

    for server in nodes:
        open_server = f"iperf3 -s '{server}' --format G"
        print ("###### " + server + " ######")
        execute_on_remote_nodes(server, username, password, open_server, supress_output=True)

        results[server] = {}

        for client in nodes:
            if client != server:
                open_client = f"iperf3 -c {server} -P 8 -t 1 | grep SUM | egrep 'sender|receiver' | awk '{{for(i=1;i<=NF;i++) if ($i ~ /bits\\/sec$/) print $(i-1) \" \" $i}}' | awk '{{print $1}}'"
                print (server + " <===> " + client)
                measured_perf = execute_on_remote_nodes(server, username, password, open_client, supress_output=False)

                lines = measured_perf.splitlines()

                results[server][client] = {}

                line_pointer = 0
                
                for line in lines:

                    if line_pointer == 0:
                        results[server][client]['tx'] = float(line)
                        line_pointer += 1

                    if line_pointer == 1:
                        results[server][client]['rx'] = float(line)

                results[server][client]['avg'] = float((float(results[server][client]['rx']) + float(results[server][client]['tx']))/2)

                time.sleep(0.1)

    #print (json.dumps(results, indent=4))


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




else:
    print ("L2 is IB")