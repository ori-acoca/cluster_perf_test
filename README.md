# network_stress_test

This tool checks network performance across all cluster nodes.
The assesses parameters are bandwidth and latency across both Ethernet and InfiniBand.

The tool expect to have a list of IP addresses in the local directory from where it is executed.
The files should be:
    - ethernet_ips.txt
    - infiniband_ips.txt
Each line in the file should be an IP address of a node's interface.

