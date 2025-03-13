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

# Get list of login-capable users
USERS=$(cat /etc/passwd | grep -v "nologin\|false" | cut -d: -f1)

for gpu in $GPUS; do
    # Check if the GPU device exists
    if [ ! -e "$gpu" ]; then
        echo "Warning: $gpu does not exist, skipping."
        continue
    fi
    
    echo "Checking $gpu:"
    
    # Get current ACLs
    CURRENT_ACLS=$(getfacl -p $gpu | grep "^user:" | cut -d: -f2)
    
    for user in $USERS; do
        # Check if user has explicit access
        if echo "$CURRENT_ACLS" | grep -q "^$user$"; then
            echo "  $user: Has explicit access (leaving as is)"
        else
            # Deny access explicitly via facl if not already granted
            echo "  $user: No access granted, setting deny"
            sudo setfacl -m u:$user:--- $gpu
        fi
    done
    echo ""
    sudo setfacl -m u:root:--- $gpu
done
