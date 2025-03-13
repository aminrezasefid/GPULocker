# GPULocker

GPULocker is a Flask-based web application designed to manage and allocate GPU resources in a multi-user environment. It provides a secure and efficient way to share limited GPU resources among users, with features for reservation, monitoring, and automatic resource management.

## Features

- **Secure Authentication**: Uses PAM authentication to verify user credentials against system accounts
- **GPU Resource Management**: Allocate specific GPU types to users for defined time periods
- **Permission Control**: Automatically manages device permissions using ACLs
- **Usage Monitoring**: Tracks active allocations and monitors GPU usage
- **Real-time GPU Status**: Provides real-time monitoring of GPU utilization and memory usage
- **Disk Usage Statistics**: Provides users with information about their disk usage
- **Automatic Cleanup**: Releases expired or idle GPU allocations
- **Admin Controls**: Special privileges for system administrators to manage all allocations
- **API Endpoints**: REST API for accessing GPU status information
- **Telegram Notifications**: Sends alerts and notifications via Telegram
- **Redis Integration**: Uses Redis for caching and data storage
- **Idle GPU Detection**: Automatically revokes access to idle GPUs

## Requirements

- Python 3.6+
- MongoDB
- Redis
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
HOST=0.0.0.0
PORT=5151
GPU_CONFIG='{"4090": [1,2,3,4]}'
LOG_FILE=gpulocker.log
LOG_LEVEL=INFO
SECRET_KEY="your_secret_key_here"
PRIVILEGED_USERS="admin1,admin2"
USER_LOCKOUT_HOURS=2
DISK_CACHE_TIMEOUT_SECONDS=1800
CHECK_FOR_IDLE_GPU_HOURS=2
GPUs_STATUS_REFRESH_RATE_SECONDS=2
MIN_GPU_UTILIZATION_PERCENT=1
MIN_GPU_MEMORY_GB=0.1
FORCE_REVOKE=False
GPU_UTILIZATION_HISTORY_DAYS=7
GPU_ACTIVITY_CHECK_MINUTES=5
REVOKE_IDLE_GPU_AFTER_HOURS=8
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
PROXY_URL="http://username:password@proxy.example.com:port"
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
TELEGRAM_CHAT_ID="your_telegram_chat_id"
```

4. Ensure MongoDB and Redis are running:
```bash
sudo systemctl start mongod
sudo systemctl start redis
```

5. Run the application:
```bash
python gpulocker.py
```

## Configuration Options

- `HOST`: Host address to bind the server
- `PORT`: Port to run the server on
- `GPU_CONFIG`: JSON string mapping GPU types to device IDs
- `LOG_FILE`: Path to the main log file
- `LOG_LEVEL`: Logging level (INFO, DEBUG, etc.)
- `SECRET_KEY`: Flask session encryption key
- `PRIVILEGED_USERS`: Comma-separated list of admin usernames
- `USER_LOCKOUT_HOURS`: Hours to lock out users after violations
- `DISK_CACHE_TIMEOUT_SECONDS`: Seconds to cache disk usage information
- `CHECK_FOR_IDLE_GPU_HOURS`: Hours between checks for idle/expired allocations
- `GPUs_STATUS_REFRESH_RATE_SECONDS`: Refresh rate in seconds for GPU status monitoring
- `MIN_GPU_UTILIZATION_PERCENT`: Minimum GPU utilization to consider active
- `MIN_GPU_MEMORY_GB`: Minimum GPU memory usage to consider active
- `GPU_UTILIZATION_HISTORY_DAYS`: Days to keep GPU utilization history
- `GPU_ACTIVITY_CHECK_MINUTES`: Minutes between GPU activity checks
- `REVOKE_IDLE_GPU_AFTER_HOURS`: Hours after which to revoke idle GPU allocations
- `FORCE_REVOKE`: When set to True, forcibly revokes GPU access without waiting for idle period (default: False)
- `REDIS_HOST`: Redis server hostname
- `REDIS_PORT`: Redis server port
- `REDIS_DB`: Redis database number
- `PROXY_URL`: HTTP proxy URL (if needed)
- `TELEGRAM_BOT_TOKEN`: Token for Telegram bot notifications
- `TELEGRAM_CHAT_ID`: Telegram chat ID for notifications

## Usage

1. Access the web interface at `http://your-server:5151`
2. Log in with your system username and password
3. View available GPUs and your current allocations
4. Request GPU resources by selecting the type and duration
5. Release GPUs when you're done using them
6. Monitor GPU utilization and memory usage in real-time on the Schedule page

## Admin Features

Administrators (users listed in `PRIVILEGED_USERS`) have additional capabilities:
- View all active allocations across users
- Release any user's GPU allocation
- Reset the entire system if needed
- Receive Telegram notifications about system events

## API Endpoints

- `/api/gpu_status`: Returns real-time GPU status information in JSON format

## Security

GPULocker uses:
- PAM authentication against system accounts
- Access control lists (ACLs) for device permissions
- Secure session management
- HTTPS support with SSL certificates (optional)

## Deployment

For production deployment, GPULocker can be run with Gunicorn:
```bash
gunicorn -c gunicorn_config.py wsgi:application
```

GPULocker is designed to be scalable and can be deployed with multiple worker processes to handle increased load:

```bash
gunicorn -c gunicorn_config.py --workers=4 wsgi:application
```

You can adjust the number of workers based on your server's CPU cores and available resources. The application uses Redis for shared state management, ensuring consistency across multiple worker processes.

## License

[MIT License](LICENSE)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.