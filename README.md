# GPULocker

GPULocker is a Flask-based web application designed to manage and allocate GPU resources in a multi-user environment. It provides a secure and efficient way to share limited GPU resources among users, with features for reservation, monitoring, and automatic resource management.

## Features

- **Secure Authentication**: Uses PAM authentication to verify user credentials against system accounts
- **GPU Resource Management**: Allocate specific GPU types to users for defined time periods
- **Permission Control**: Automatically manages device permissions using ACLs
- **Usage Monitoring**: Tracks active allocations and monitors GPU usage
- **Disk Usage Statistics**: Provides users with information about their disk usage
- **Automatic Cleanup**: Releases expired or idle GPU allocations
- **Admin Controls**: Special privileges for system administrators to manage all allocations

## Requirements

- Python 3.6+
- MongoDB
- NVIDIA GPUs with nvidia-smi
- Linux system with sudo access for permission management
- Python packages (see requirements.txt)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/gpulocker.git
cd gpulocker
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with the following configuration:

```
SECRET_KEY=your_secret_key_here
GPU_CONFIG={'A100': [0, 1, 2, 3], 'V100': [4, 5, 6, 7]}
PRIVILEGED_USERS=admin1,admin2
USER_PENALTY=24
CHECK_FOR_IDLE_GPU=6
DISK_CACHE_TIMEOUT=600
HOST=0.0.0.0
PORT=5151
```

4. Ensure MongoDB is running:
```bash
sudo systemctl start mongod
```

5. Run the application:
```bash
python gpulocker.py
```

## Configuration Options

- `SECRET_KEY`: Flask session encryption key
- `GPU_CONFIG`: Dictionary mapping GPU types to device IDs
- `PRIVILEGED_USERS`: Comma-separated list of admin usernames
- `USER_PENALTY`: Hours to wait after expiration before forcibly releasing GPUs
- `CHECK_FOR_IDLE_GPU`: Hours between checks for idle/expired allocations
- `DISK_CACHE_TIMEOUT`: Seconds to cache disk usage information
- `HOST`: Host address to bind the server
- `PORT`: Port to run the server on

## Usage

1. Access the web interface at `https://your-server:5151`
2. Log in with your system username and password
3. View available GPUs and your current allocations
4. Request GPU resources by selecting the type and duration
5. Release GPUs when you're done using them

## Admin Features

Administrators (users listed in `PRIVILEGED_USERS`) have additional capabilities:
- View all active allocations across users
- Release any user's GPU allocation
- Reset the entire system if needed

## Security

GPULocker uses:
- HTTPS with self-signed certificates by default
- PAM authentication against system accounts
- Access control lists (ACLs) for device permissions
- Secure session management

## License

[MIT License](LICENSE)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.