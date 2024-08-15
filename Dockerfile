# Use the latest Ubuntu LTS as the base image
FROM ubuntu:22.04

# Install necessary packages
RUN apt-get update && \
    apt-get install -y \
    openssh-server \
    iperf3 \
    vim \
    tcpdump \
    git \
    build-essential \
    rdma-core \
    iputils-ping && \
    rm -rf /var/lib/apt/lists/*

# Create user and set password
RUN useradd -m weka && echo 'weka:weka.io' | chpasswd

# Configure SSH
RUN mkdir /var/run/sshd

# Set SSH to allow password authentication
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

# Expose SSH port
EXPOSE 22

# Start SSH daemon
CMD ["/usr/sbin/sshd", "-D"]

