#!/bin/bash

# Check if GPU IDs are provided as arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 <gpu_id1> [gpu_id2] ..."
    echo "Example: $0 1 2 3 4"
    exit 1
fi

# Construct GPU device paths from provided IDs
GPUS=""
for id in "$@"; do
    GPUS="$GPUS /dev/nvidia$id"
done

for gpu in $GPUS; do
    # Check if the GPU device exists
    if [ ! -e "$gpu" ]; then
        echo "Warning: $gpu does not exist, skipping."
        continue
    fi
    
    echo "Resetting ACLs for $gpu"
    
    # Remove all ACL entries for the GPU
    sudo setfacl -b $gpu
    
    echo "  ACL rules removed for $gpu"
done

echo "GPU ACL rules have been reset."
